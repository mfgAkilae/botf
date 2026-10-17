"""Resync spike (test build only), docs/resync_design_draft.md section 7.

A small state machine, driven by the test tool (tools/spike.py) through poke-able fields, transfers the host's
game state to every client with the stock messages 0x89 (wait dialog) and 0x72 (save file) and applies it without
closing the DirectPlay transport. No protocol: the tool copies the expected length/CRC32 from the host into the
clients and writes the states.

  sp_state  0 IDLE, 1 PREPARE (host), 2 ARMED (all), 3 SEND (host), 4 DRAIN, 5 DONE

Everything lives in the enlarged test shim section (build_test.py --spike): code at sec+0x200, data at sec+0x2000.
Chained into two netfix caves: the dispatcher hook 0x50a709 (Fix B) and the timer hook 0x4b9f6a (Fix K).
"""
import struct

CODE_OFF, DATA_OFF, SECTION_SIZE = 0x200, 0x2000, 0xa000

# data fields (offsets from the data base)
FIELDS = {
    'sp_state': 0x00, 'sp_len': 0x04, 'sp_crc': 0x08, 'rs_guard': 0x0c, 'rs_apply': 0x10,
    'tok_valid': 0x14, 'tok_w': 0x18, 'tok_l': 0x1c, 'saved_2994': 0x20, 'q_count': 0x24,
    'flag_open': 0x28, 'flag_tail': 0x2c, 'apply_result': 0x30, 'last_fail': 0x34, 'mode72': 0x38,
    'prep_done': 0x3c, 'loaded_mask': 0x40, 'log_n': 0x44, 'rx_n': 0x48, 'test_n': 0x4c, 'test_seq': 0x50,
    'trx_n': 0x54, 'cnt_queued': 0x58, 'cnt_redispatch': 0x5c, 'cnt_retired': 0x60, 'cnt_applies': 0x64,
    'last_result': 0x68, 'tmp_len': 0x6c, 'tmp_crc': 0x70, 'tmp_buf': 0x74, 'cnt_tokpass': 0x78,
    'cur_type': 0x7c,
    'lg': 0x80,            # 6 staging dwords for the next log entry
    'cnt_uifix': 0x98,     # turn UI re-enabled after a load (this machine had ended the turn)
    'cnt_incident': 0x9c,  # incident popup closed after the load had reset the incident list
    'queue': 0xa0,         # 4 x (type, wParam, lParam, 0)
    'namebuf': 0xe0,       # 0x20
    'rngbuf': 0x100,       # 0x130: the 0x71 message layout (turn, RNG block at +4, ...)
    'scratch': 0x240,      # 0x40: body of a retired 0x89 / a received test message
    'testbody': 0x280,     # 8: (seq, own player id)
    'inc_open': 0x290,     # incident popup open when the last apply started (FUN_00505320)
    'cnt_infobox': 0x294,  # galaxy-map info box shown for a system without a valid production kind
    'snap_turn': 0x298,    # turn of the last turn-start snapshot (initially -1)
    'ts_turn': 0x29c,      # host: turn of the last turn-start save (initially -1)
    'own_emp': 0x2a0,      # local empire at the snapshot
    'own_n': 0x2a4,        # system slots in the snapshot
    'cnt_ownrestore': 0x2a8,  # production records written back after loads
    'apply_turn': 0x2ac,   # turn when the last apply started
    'prep_fallback': 0x2b0,   # PREPARE had to save now (no turn-start save of this turn)
    'logring': 0x300,      # 128 x 32: (n, kind, a, b, c, d, e, f)
    'rxring': 0x1300,      # 256 x 12: (wParam, lParam, type) of every received 0x400
    'trxring': 0x1f00,     # 256 x 8: (wParam, seq) of every received test message
    'ownflag': 0x2800,     # MAXSYS bytes: system i belonged to the local empire at the snapshot
    'ownbuf': 0x2a00,      # MAXSYS x 0x28: system +0x80..+0xa7 (current and last production record)
}
MAXSYS = 512
DATA_SIZE = 0x2a00 + MAXSYS * 0x28
LOG_N, RX_N, TRX_N = 128, 256, 256
QMAX = 4
TEST_MSG = 0x94            # not a stock id and not one of the planned resync ids 0x8a..0x93

# log kinds
K_PREP, K_SENT, K_QUEUED, K_REDISP, K_RETIRE, K_RAW, K_APPLY, K_FAIL, K_DONE, K_TEST = range(1, 11)
# failure codes
F_RAWLEN, F_RAWCRC, F_OVERFLOW, F_FLAG, F_FILE, F_TOKEN, F_RETIRE = range(1, 8)


def apply(p, sec, info, pump_override=True, owner_mode='restart'):
    from asmutil import asm, call_rel, jmp_rel        # keystone only for building; tools/spike.py needs just the layout
    assert owner_mode in ('restart', 'snapshot')
    snapshot = owner_mode == 'snapshot'
    assert CODE_OFF < DATA_OFF and DATA_OFF + DATA_SIZE <= SECTION_SIZE
    D = sec + DATA_OFF
    a = {k: D + v for k, v in FIELDS.items()}
    lg = a['lg']
    code = sec + CODE_OFF
    out = {}

    def put(name, text):
        nonlocal code
        b = asm(text, code)
        assert code + len(b) <= sec + DATA_OFF, name
        p.write(code, b)
        out[name] = code
        code += (len(b) + 15) & ~15
        return out[name]

    def log(kind, **vals):
        """inline: stage up to six values (registers or immediates) and append a log entry; keeps all registers"""
        s = ''.join(f'    mov dword ptr [{lg + 4 * "abcdef".index(k):#x}], {v}\n' for k, v in vals.items())
        return s + f'    push eax\n    mov eax, {kind}\n    call {logf:#x}\n    pop eax\n'

    def fail(codeval):
        return (f'    mov dword ptr [{a["last_fail"]:#x}], {codeval}\n'
                + log(K_FAIL, a=codeval))

    # ---- log append: eax = kind, the staged values at lg ------------------------------------------------
    logf = put('log', f'''
        pushad
        pushfd
        cld
        mov edx, dword ptr [{a['log_n']:#x}]
        and edx, {LOG_N - 1}
        shl edx, 5
        lea edi, [edx + {a['logring']:#x}]
        mov ecx, dword ptr [{a['log_n']:#x}]
        mov dword ptr [edi], ecx
        mov dword ptr [edi + 4], eax
        add edi, 8
        mov esi, {lg:#x}
        mov ecx, 6
        rep movsd dword ptr es:[edi], dword ptr [esi]
        inc dword ptr [{a['log_n']:#x}]
        mov edi, {lg:#x}
        xor eax, eax
        mov ecx, 6
        rep stosd
        popfd
        popad
        ret
    ''')

    # ---- CRC32 (bitwise, poly 0xEDB88320, as zlib.crc32): eax = data, edx = length -> eax ----------------
    crc32 = put('crc32', '''
        push ecx
        push edx
        push esi
        push edi
        mov esi, eax
        mov ecx, edx
        mov eax, 0xffffffff
        test ecx, ecx
        je crc_end
    crc_byte:
        movzx edx, byte ptr [esi]
        xor eax, edx
        mov edi, 8
    crc_bit:
        shr eax, 1
        jnc crc_nopoly
        xor eax, 0xedb88320
    crc_nopoly:
        dec edi
        jne crc_bit
        inc esi
        dec ecx
        jne crc_byte
    crc_end:
        not eax
        pop edi
        pop esi
        pop edx
        pop ecx
        ret
    ''')

    # ---- length and CRC32 of auto.sav (the reads of FUN_0050de40): eax = 1 ok / 0 missing ----------------
    filestat = put('filestat', f'''
        push ebx
        push ecx
        push edx
        push esi
        push edi
        mov eax, -0xd
        mov edx, {a['namebuf']:#x}
        call 0x438590
        mov eax, {a['namebuf']:#x}
        mov edx, 0x583870
        call 0x5165c2
        test eax, eax
        je fs_fail
        mov esi, eax
        mov eax, esi
        xor edx, edx
        mov ebx, 2
        call 0x516712
        mov eax, esi
        call 0x516822
        mov edi, eax
        mov eax, esi
        xor edx, edx
        xor ebx, ebx
        call 0x516712
        mov eax, edi
        mov ebx, 1
        call 0x492ed0
        test eax, eax
        je fs_close
        mov dword ptr [{a['tmp_buf']:#x}], eax
        mov edx, edi
        mov ebx, 1
        mov ecx, esi
        call 0x51687b
        mov eax, dword ptr [{a['tmp_buf']:#x}]
        mov edx, edi
        call {crc32:#x}
        mov dword ptr [{a['tmp_crc']:#x}], eax
        mov dword ptr [{a['tmp_len']:#x}], edi
        mov eax, dword ptr [{a['tmp_buf']:#x}]
        call 0x492e60
        mov eax, esi
        call 0x516a80
        mov eax, 1
        jmp fs_out
    fs_close:
        mov eax, esi
        call 0x516a80
    fs_fail:
        xor eax, eax
    fs_out:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    ''')

    # ---- turn-start snapshot of the local empire's production records (finding E, see below) -----------------
    ob, of = a['ownbuf'], a['ownflag']
    ownsave = put('ownsave', f'''
        pushad
        movzx eax, byte ptr [0x5a2b2a]
        mov dword ptr [{a['own_emp']:#x}], eax
        mov dword ptr [{a['own_n']:#x}], 0
        mov esi, dword ptr [0x5a36c8]
        test esi, esi
        je os_done
        movzx ecx, word ptr [0x5a36bc]
        cmp ecx, {MAXSYS}
        jbe os_n
        mov ecx, {MAXSYS}
    os_n:
        mov dword ptr [{a['own_n']:#x}], ecx
        xor ebx, ebx
        cld
    os_loop:
        cmp ebx, ecx
        jae os_done
        mov byte ptr [ebx + {of:#x}], 0
        movzx eax, byte ptr [esi + 0x4c]
        cmp eax, dword ptr [{a['own_emp']:#x}]
        jne os_next
        mov byte ptr [ebx + {of:#x}], 1
        push ecx
        push esi
        imul edi, ebx, 0x28
        add edi, {ob:#x}
        add esi, 0x80
        mov ecx, 10
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop esi
        pop ecx
    os_next:
        add esi, 0x328
        inc ebx
        jmp os_loop
    os_done:
        popad
        ret
    ''')
    ownrest = put('ownrest', f'''
        pushad
        mov ecx, dword ptr [{a['own_n']:#x}]
        movzx eax, word ptr [0x5a36bc]
        cmp ecx, eax
        jbe or_n
        mov ecx, eax
    or_n:
        mov esi, dword ptr [0x5a36c8]
        test esi, esi
        je or_done
        xor ebx, ebx
        cld
    or_loop:
        cmp ebx, ecx
        jae or_done
        cmp byte ptr [ebx + {of:#x}], 0
        je or_next
        movzx eax, byte ptr [esi + 0x4c]
        cmp eax, dword ptr [{a['own_emp']:#x}]
        jne or_next
        push ecx
        push esi
        lea edi, [esi + 0x80]
        imul esi, ebx, 0x28
        add esi, {ob:#x}
        mov ecx, 10
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop esi
        pop ecx
        inc dword ptr [{a['cnt_ownrestore']:#x}]
    or_next:
        add esi, 0x328
        inc ebx
        jmp or_loop
    or_done:
        popad
        ret
    ''')

    # ---- apply helper (section 4.4 steps 1-6; LOADED replaced by a log entry) ------------------------------
    # Spike finding (procedure 2): END TURN disables the turn UI (FUN_004b90a0, flags [0x594d20]/[0x593250]) and
    # only the end of turn processing enables it again (FUN_004b9110). A machine that had ended the turn before
    # the transfer kept a dead END TURN button after the load. The common cleanup now enables the turn UI when
    # the load has reset the turn state ([0x5a291c] == 0) and the UI is still disabled.
    rb = a['rngbuf']
    helper = put('helper', f'''
        pushad
        mov dword ptr [{a['rs_apply']:#x}], 1
        call 0x505320
        mov dword ptr [{a['inc_open']:#x}], eax
        mov eax, dword ptr [0x5a2994]
        mov dword ptr [{a['saved_2994']:#x}], eax
        cmp dword ptr [0x597508], 0
        jne h_dlg
        call 0x50d070
    h_dlg:
        mov dword ptr [0x5a2990], 0
        mov dword ptr [0x5a2994], 1
        mov dword ptr [{a['flag_open']:#x}], 0
        mov dword ptr [{a['flag_tail']:#x}], 0
        mov dword ptr [{a['loaded_mask']:#x}], 0xffffffff
        mov eax, dword ptr [0x5a2918]
        mov dword ptr [{a['apply_turn']:#x}], eax
        call 0x50da70
        mov eax, dword ptr [{a['saved_2994']:#x}]
        mov dword ptr [0x5a2994], eax
        mov eax, dword ptr [0x5fd978]
        mov dword ptr [0x5a2990], eax
        xor ecx, ecx
    h_slot:
        mov eax, dword ptr [ecx + 0x5b4870]
        test eax, eax
        je h_slotnext
        call 0x51b520
        mov eax, dword ptr [ecx + 0x5b4870]
        xor edx, edx
        call 0x51b450
        mov dword ptr [ecx + 0x5b4870], 0
        mov byte ptr [ecx + 0x5b4874], 0xff
    h_slotnext:
        add ecx, 8
        cmp ecx, 0x20
        jb h_slot
        call 0x510230
        cmp dword ptr [0x5a291c], 0
        jne h_ui
        cmp dword ptr [0x592c78], 0
        je h_ui
        mov eax, dword ptr [0x594d20]
        or eax, dword ptr [0x593250]
        je h_ui
        call 0x4b9110
        inc dword ptr [{a['cnt_uifix']:#x}]
    h_ui:
        mov dword ptr [{a['rs_apply']:#x}], 0
        mov dword ptr [{a['mode72']:#x}], 0
        inc dword ptr [{a['cnt_applies']:#x}]
        cmp dword ptr [{a['flag_open']:#x}], 0
        je h_fail
        cmp dword ptr [{a['flag_tail']:#x}], 0
        je h_fail
        mov eax, {rb:#x}
        xor edx, edx
        mov ebx, 0x130
        call 0x51d853
        mov eax, dword ptr [0x5a2918]
        mov dword ptr [{rb:#x}], eax
        mov esi, {rb + 4:#x}
        mov edx, 0x597612
        mov ebx, 0x597614
        call 0x508080
        mov esi, {rb + 4:#x}
        mov eax, 0x597610
        mov edx, 0x597612
        mov ebx, 0x597614
        call 0x447b40
        call 0x43db00
        mov word ptr [0x597616], ax
        call 0x45d570
        mov word ptr [0x597618], ax
        xor eax, eax
        mov dword ptr [{rb + 8:#x}], eax
        mov dword ptr [{rb + 0xc:#x}], eax
        mov dword ptr [{rb + 0x10:#x}], eax
        mov dword ptr [{rb + 0x14:#x}], eax
        mov dword ptr [{rb + 0x18:#x}], eax
        mov eax, {rb + 4:#x}
        mov edx, 0x120
        call {crc32:#x}
        mov esi, eax
        movzx eax, word ptr [0x597618]
        movzx edx, byte ptr [0x597504]
        shl edx, 16
        or eax, edx
        movzx edx, byte ptr [{a['loaded_mask']:#x}]
        shl edx, 24
        or eax, edx
        mov ecx, dword ptr [0x597610]
        mov edx, dword ptr [0x597614]
        movzx edi, byte ptr [0x5a2b28]
        mov ebx, dword ptr [0x5a2918]
{log(K_APPLY, a='ecx', b='edx', c='eax', d='esi', e='ebx', f='edi')}
        mov dword ptr [{a['apply_result']:#x}], 1
        popad
        ret
    h_fail:
        mov eax, dword ptr [{a['flag_open']:#x}]
        mov edx, dword ptr [{a['flag_tail']:#x}]
        mov dword ptr [{a['last_fail']:#x}], {F_FLAG}
{log(K_FAIL, a=F_FLAG, b='eax', c='edx')}
        mov dword ptr [{a['apply_result']:#x}], 2
        popad
        ret
    ''')

    # ---- section 4.2: queue 0x89/0x72 while sp_state is 2..4, one-shot token, test messages ---------------
    # at 0x50a709: AX = message id, ECX = window message, ESI = wParam, EDI = lParam, [esp] = scratch word
    disp = put('disp', f'''
        cmp ecx, 0x400
        jne d_chain
        pushad
        mov edx, dword ptr [{a['rx_n']:#x}]
        and edx, {RX_N - 1}
        lea edx, [edx + edx*2]
        shl edx, 2
        mov dword ptr [edx + {a['rxring']:#x}], esi
        mov dword ptr [edx + {a['rxring'] + 4:#x}], edi
        movzx eax, ax
        mov dword ptr [edx + {a['rxring'] + 8:#x}], eax
        inc dword ptr [{a['rx_n']:#x}]
        popad
        cmp ax, {TEST_MSG:#x}
        je d_test
        cmp ax, 0x89
        je d_cand
        cmp ax, 0x72
        jne d_chain
    d_cand:
        cmp dword ptr [{a['sp_state']:#x}], 2
        jb d_chain
        cmp dword ptr [{a['sp_state']:#x}], 4
        ja d_chain
        cmp dword ptr [{a['tok_valid']:#x}], 0
        je d_queue
        cmp esi, dword ptr [{a['tok_w']:#x}]
        jne d_queue
        cmp edi, dword ptr [{a['tok_l']:#x}]
        jne d_queue
        mov dword ptr [{a['tok_valid']:#x}], 0
        inc dword ptr [{a['cnt_tokpass']:#x}]
        mov word ptr [esp], ax
        mov eax, dword ptr [esp]
        jmp 0x50a710
    d_queue:
        cmp dword ptr [{a['q_count']:#x}], {QMAX}
        jae d_over
        pushad
        mov edx, dword ptr [{a['q_count']:#x}]
        shl edx, 4
        movzx eax, ax
        mov dword ptr [edx + {a['queue']:#x}], eax
        mov dword ptr [edx + {a['queue'] + 4:#x}], esi
        mov dword ptr [edx + {a['queue'] + 8:#x}], edi
        inc dword ptr [{a['q_count']:#x}]
        inc dword ptr [{a['cnt_queued']:#x}]
        mov edx, dword ptr [{a['q_count']:#x}]
{log(K_QUEUED, a='eax', b='esi', c='edi', d='edx')}
        popad
        cmp dword ptr [{a['sp_state']:#x}], 2
        jne d_handled
        mov dword ptr [{a['sp_state']:#x}], 4
    d_handled:
        jmp 0x50a762
    d_over:
{fail(F_OVERFLOW)}
        mov dword ptr [{a['apply_result']:#x}], 2
        jmp 0x50a762
    d_test:
        pushad
        mov eax, edi
        mov edx, esi
        call 0x519910
        cmp eax, 0x40
        ja d_testout
        mov eax, edi
        mov edx, {a['scratch']:#x}
        mov ebx, esi
        call 0x519900
        mov edx, dword ptr [{a['trx_n']:#x}]
        and edx, {TRX_N - 1}
        shl edx, 3
        mov dword ptr [edx + {a['trxring']:#x}], esi
        mov eax, dword ptr [{a['scratch']:#x}]
        mov dword ptr [edx + {a['trxring'] + 4:#x}], eax
        inc dword ptr [{a['trx_n']:#x}]
    d_testout:
        popad
        jmp 0x50a762
    d_chain:
        jmp {info['dispatch']:#x}
    ''')
    # netfix put 'jmp dispatch; nop; nop' at 0x50a709; the spike cave runs first and falls through to it
    p.patch(0x50a709, (jmp_rel(0x50a709, info['dispatch']) + b'\x90\x90').hex(), jmp_rel(0x50a709, disp) + b'\x90\x90')

    # ---- raw-buffer check at 0x50dd76 (eax = ecx = buffer, edx = ebp = length) ------------------------------
    raw = put('raw', f'''
        cmp dword ptr [{a['mode72']:#x}], 0
        je r_stock
        pushad
        mov ebx, eax
        mov ecx, dword ptr [{a['sp_len']:#x}]
        mov esi, dword ptr [{a['sp_crc']:#x}]
        cmp edx, ecx
        jne r_badlen
        mov eax, ebx
        call {crc32:#x}
{log(K_RAW, a='edx', b='eax', c='ecx', d='esi')}
        cmp eax, esi
        jne r_badcrc
        popad
        call 0x50dd90
        jmp 0x50dd7b
    r_badlen:
{log(K_RAW, a='edx', b=0, c='ecx', d='esi')}
{fail(F_RAWLEN)}
        jmp r_fail
    r_badcrc:
{fail(F_RAWCRC)}
    r_fail:
        popad
        call 0x492e60
        mov dword ptr [{a['mode72']:#x}], 0
        mov dword ptr [{a['apply_result']:#x}], 2
        cmp dword ptr [0x597508], 0
        je r_nodlg
        call 0x50d010
    r_nodlg:
        jmp 0x50dd80
    r_stock:
        call 0x50dd90
        jmp 0x50dd7b
    ''')
    p.patch(0x50dd76, 'e815000000', jmp_rel(0x50dd76, raw))

    # ---- 0x50dd7b: the apply helper for the spike's 0x72, the stock apply otherwise ---------------------
    sel = put('applysel', f'''
        cmp dword ptr [{a['mode72']:#x}], 0
        je 0x50da70
        jmp {helper:#x}
    ''')
    p.patch(0x50dd7b, 'e8f0fcffff', call_rel(0x50dd7b, sel))

    # ---- FUN_0043d0d0: no lobby-score messages and no transport teardown while the helper applies -----------
    for site, target in ((0x43d0f2, 0x50d670), (0x43d0f7, 0x519b80)):
        c = put('td_%x' % site, f'''
            cmp dword ptr [{a['rs_apply']:#x}], 0
            je td_real
            ret
        td_real:
            jmp {target:#x}
        ''')
        p.patch(site, call_rel(site, target).hex(), call_rel(site, c))

    # ---- load flags: file opened (0x4387fb) and load completed (0x4389c0) -------------------------------
    fo = put('flagopen', f'''
        cmp eax, 1
        jne fo_no
        mov dword ptr [{a['flag_open']:#x}], 1
        jmp 0x438805
    fo_no:
        jmp 0x438800
    ''')
    p.patch(0x4387fb, '83f8017405', jmp_rel(0x4387fb, fo))
    tail_restore = f'''
        cmp dword ptr [{a['rs_apply']:#x}], 0
        je ft_out
        mov eax, dword ptr [{a['snap_turn']:#x}]
        cmp eax, dword ptr [{a['apply_turn']:#x}]
        jne ft_out
        call {ownrest:#x}''' if snapshot else ''
    ft = put('flagtail', f'''
        call 0x51c9c0
        mov dword ptr [{a['flag_tail']:#x}], 1
        push eax
        movzx eax, byte ptr [0x5a2b28]
        mov dword ptr [{a['loaded_mask']:#x}], eax
{tail_restore}
    ft_out:
        pop eax
        jmp 0x4389c5
    ''')
    p.patch(0x4389c0, 'e8fb3f0e00', jmp_rel(0x4389c0, ft))

    # ---- spike finding (live test): an open incident popup survives the load --------------------------------
    # The load resets the turn's incident list (FUN_0044b8e0 from 0x43897b: [0x58fd70] = [0x58fd74] = 0) but the
    # incident popup stays open. FUN_0050da70 then switches screens (0x50dc8c -> FUN_004b9180 -> FUN_005001b0), which
    # closes the popup and advances the list in FUN_0044ce40: FUN_0051b7a0(NULL) -> access violation at 0x51b7a1.
    # With an empty list the advance now ends the incident sequence the stock way (0x44ce6b: both 0, FUN_00492720).
    inc = put('incident', f'''
        mov eax, dword ptr [0x58fd74]
        test eax, eax
        jne in_next
        inc dword ptr [{a['cnt_incident']:#x}]
        xor ecx, ecx
        jmp 0x44ce6b
    in_next:
        call 0x51b7a0
        jmp 0x44ce4b
    ''')
    # 0x44ce41: mov eax,[0x58fd74] / call 0x51b7a0 (10 bytes)
    p.patch(0x44ce41, 'a174fd5800' + call_rel(0x44ce46, 0x51b7a0).hex(), jmp_rel(0x44ce41, inc) + b'\x90' * 5)

    # ---- spike finding E (live runs): the owners' production records -------------------------------------------
    # System +0x80..+0xa7 (current and last production record) has an owner form and a non-owner form between
    # turns (the documented mode 1 / mode 2 kill difference, outside every CRC). A load gives every machine the
    # host's forms: owners then asserted in their own UI (galaxy-map info box, infobox.c line 1161 at 0x4e9923;
    # system screen, redifice.c line 267 with structure id 0x7fff). Keeping each owner's current records across
    # the load desynchronised (they held the effect of current-turn input that the load drops everywhere else).
    # Consistent is the configuration of a turn start: the host transfers its turn-start state (a save in the first
    # loop-top step after its turn processing) and every machine takes a snapshot of its own systems' records at
    # the same point and writes it back at the end of the load. The info box guard below is only a safety net
    # (its counter shows whether it was needed): the assert's ignore path 0x4e992c, default text set at 0x4e98f6.
    ibox = put('infobox', f'''
        inc dword ptr [{a['cnt_infobox']:#x}]
        jmp 0x4e992c
    ''')
    # 0x4e990e: mov ebp,0x581a5c (5 bytes), first instruction of the assert loop after the kind check at 0x4e9905
    p.patch(0x4e990e, 'bd5c1a5800', jmp_rel(0x4e990e, ibox))

    # ---- finding E, stock variant: restart the local empire's production after the load ------------------------
    # Every machine of a stock lobby resume takes the non-resume branch of FUN_0050da70 and calls FUN_0043a0a0(local
    # empire) at 0x50dbc9 (observed with breakpoints), which derives the owner form of the own systems' production
    # records from the loaded state. The helper forces the resume branch (mask from the file) and so skipped it.
    # The resume branch now makes the same call after the load, with the same condition, while rs_apply is held.
    if not snapshot:
        rst = put('restart', f'''
            cmp dword ptr [{a['rs_apply']:#x}], 0
            je rs_out
            pushad
            movzx ecx, byte ptr [0x5a2b2a]
            mov edx, 1
            shl edx, cl
            movzx eax, byte ptr [0x597504]
            test edx, eax
            je rs_skip
            mov eax, ecx
            call 0x43a0a0
            inc dword ptr [{a['cnt_ownrestore']:#x}]
        rs_skip:
            popad
        rs_out:
            jmp 0x50dbce
        ''')
        # 0x50dd00: jmp 0x50dbce at the end of the resume branch (after the load, local empire and mask restored)
        p.patch(0x50dd00, jmp_rel(0x50dd00, 0x50dbce).hex(), jmp_rel(0x50dd00, rst))

    # ---- pump override at 0x4024d8: idle exit while rs_guard -------------------------------------------
    pump = put('pump', f'''
        cmp dword ptr [{a['rs_guard']:#x}], 0
        jne 0x402512
        cmp esi, dword ptr [0x5a28d4]
        jmp 0x4024de
    ''')
    if pump_override:          # off only for the negative control (build_test.py --spike-nopump)
        p.patch(0x4024d8, '3b35d4285a00', jmp_rel(0x4024d8, pump) + b'\x90')

    # ---- compare-loop gate 0x510002: no compares while sp_state is 2..4 -----------------------------------
    gate = put('cmpgate', f'''
        cmp dword ptr [{a['sp_state']:#x}], 2
        jb g_normal
        cmp dword ptr [{a['sp_state']:#x}], 4
        ja g_normal
        jmp 0x51002d
    g_normal:
        cmp dword ptr [ebp + 0x5ccfc0], -1
        jmp 0x510009
    ''')
    p.patch(0x510002, '83bdc0cf5c00ff', jmp_rel(0x510002, gate) + b'\x90\x90')

    # ---- timer END TURN (Fix K cave) deferred while sp_state is 2..4 -----------------------------------
    tim = put('timer', f'''
        cmp dword ptr [{a['sp_state']:#x}], 2
        jb t_pass
        cmp dword ptr [{a['sp_state']:#x}], 4
        ja t_pass
        jmp 0x4b9ec0
    t_pass:
        jmp {info['timerguard']:#x}
    ''')
    p.patch(0x4b9f6a, (jmp_rel(0x4b9f6a, info['timerguard']) + b'\x90' * 5).hex(), jmp_rel(0x4b9f6a, tim) + b'\x90' * 5)

    # ---- loop-top step functions --------------------------------------------------------------------------
    use_ts = f'''
        mov eax, dword ptr [0x5a2918]
        cmp eax, dword ptr [{a['ts_turn']:#x}]
        je pr_have
        mov dword ptr [{a['prep_fallback']:#x}], 1''' if snapshot else ''
    prepare = put('prepare', f'''
{use_ts}
        mov al, byte ptr [0x5a2b28]
        mov byte ptr [0x5a2998], al
        mov eax, -0xd
        call 0x438630
    pr_have:
        call {filestat:#x}
        test eax, eax
        je pr_fail
        mov eax, dword ptr [{a['tmp_len']:#x}]
        mov dword ptr [{a['sp_len']:#x}], eax
        mov edx, dword ptr [{a['tmp_crc']:#x}]
        mov dword ptr [{a['sp_crc']:#x}], edx
        movzx ecx, byte ptr [0x5a2998]
        mov ebx, dword ptr [0x5a2918]
{log(K_PREP, a='eax', b='edx', c='ecx', d='ebx')}
        ret
    pr_fail:
{fail(F_FILE)}
        mov dword ptr [{a['apply_result']:#x}], 2
        mov dword ptr [{a['sp_state']:#x}], 5
        ret
    ''')

    send = put('send', f'''
        call {filestat:#x}
        test eax, eax
        je se_fail
        mov eax, 0x89
        call 0x5199c0
        mov eax, -0xd
        xor edx, edx
        call 0x50de40
        mov eax, dword ptr [{a['tmp_len']:#x}]
        mov edx, dword ptr [{a['tmp_crc']:#x}]
{log(K_SENT, a='eax', b='edx')}
        call {helper:#x}
        mov dword ptr [{a['sp_state']:#x}], 4
        ret
    se_fail:
{fail(F_FILE)}
        mov dword ptr [{a['apply_result']:#x}], 2
        mov dword ptr [{a['sp_state']:#x}], 5
        ret
    ''')

    retire = put('retire', f'''
        mov eax, dword ptr [{a['tok_l']:#x}]
        mov edx, dword ptr [{a['tok_w']:#x}]
        call 0x519920
        movzx esi, ax
        cmp esi, 0x89
        jne rt_bad
        mov eax, dword ptr [{a['tok_l']:#x}]
        mov edx, dword ptr [{a['tok_w']:#x}]
        call 0x519910
        mov edi, eax
        cmp edi, 0x40
        ja rt_bad
        mov eax, dword ptr [{a['tok_l']:#x}]
        mov edx, {a['scratch']:#x}
        mov ebx, dword ptr [{a['tok_w']:#x}]
        call 0x519900
        inc dword ptr [{a['cnt_retired']:#x}]
        mov eax, dword ptr [{a['tok_w']:#x}]
        mov edx, dword ptr [{a['tok_l']:#x}]
{log(K_RETIRE, a='eax', b='edx', c='esi', d='edi')}
        ret
    rt_bad:
        mov eax, dword ptr [{a['tok_w']:#x}]
        mov edx, dword ptr [{a['tok_l']:#x}]
        mov dword ptr [{a['last_fail']:#x}], {F_RETIRE}
{log(K_FAIL, a=F_RETIRE, b='eax', c='edx', d='esi')}
        ret
    ''')

    q = a['queue']
    drain = put('drain', f'''
        cmp dword ptr [{a['q_count']:#x}], 0
        je dr_empty
        mov eax, dword ptr [{q:#x}]
        mov dword ptr [{a['cur_type']:#x}], eax
        mov eax, dword ptr [{q + 4:#x}]
        mov dword ptr [{a['tok_w']:#x}], eax
        mov eax, dword ptr [{q + 8:#x}]
        mov dword ptr [{a['tok_l']:#x}], eax
        cld
        mov esi, {q + 0x10:#x}
        mov edi, {q:#x}
        mov ecx, {(QMAX - 1) * 4}
        rep movsd dword ptr es:[edi], dword ptr [esi]
        xor eax, eax
        mov dword ptr [{q + (QMAX - 1) * 0x10:#x}], eax
        mov dword ptr [{q + (QMAX - 1) * 0x10 + 4:#x}], eax
        mov dword ptr [{q + (QMAX - 1) * 0x10 + 8:#x}], eax
        dec dword ptr [{a['q_count']:#x}]
        mov dword ptr [{a['tok_valid']:#x}], 1
        cmp dword ptr [{a['cur_type']:#x}], 0x72
        jne dr_go
        mov dword ptr [{a['mode72']:#x}], 1
    dr_go:
        mov eax, dword ptr [{a['cur_type']:#x}]
        mov edx, dword ptr [{a['tok_w']:#x}]
        mov ebx, dword ptr [{a['tok_l']:#x}]
        mov ecx, dword ptr [{a['q_count']:#x}]
{log(K_REDISP, a='eax', b='edx', c='ebx', d='ecx')}
        mov eax, 0x400
        call 0x50a6e0
        inc dword ptr [{a['cnt_redispatch']:#x}]
        cmp dword ptr [{a['tok_valid']:#x}], 0
        je dr_used
        mov dword ptr [{a['tok_valid']:#x}], 0
        mov dword ptr [{a['mode72']:#x}], 0
        mov eax, dword ptr [{a['cur_type']:#x}]
        mov dword ptr [{a['last_fail']:#x}], {F_TOKEN}
{log(K_FAIL, a=F_TOKEN, b='eax')}
        cmp eax, 0x72
        jne dr_ret
        mov dword ptr [{a['apply_result']:#x}], 2
        ret
    dr_used:
        cmp dword ptr [{a['cur_type']:#x}], 0x89
        jne dr_ret
        call {retire:#x}
    dr_ret:
        ret
    dr_empty:
        cmp dword ptr [{a['apply_result']:#x}], 0
        je dr_ret
        mov dword ptr [{a['sp_state']:#x}], 5
        ret
    ''')

    done = put('done', f'''
        mov eax, dword ptr [{a['apply_result']:#x}]
        mov dword ptr [{a['last_result']:#x}], eax
        mov edx, dword ptr [{a['q_count']:#x}]
        mov ecx, dword ptr [{a['tok_valid']:#x}]
        mov ebx, dword ptr [{a['last_fail']:#x}]
{log(K_DONE, a='eax', b='edx', c='ecx', d='ebx')}
        xor eax, eax
        mov dword ptr [{a['rs_guard']:#x}], eax
        mov dword ptr [{a['flag_open']:#x}], eax
        mov dword ptr [{a['flag_tail']:#x}], eax
        mov dword ptr [{a['tok_valid']:#x}], eax
        mov dword ptr [{a['q_count']:#x}], eax
        mov dword ptr [{a['mode72']:#x}], eax
        mov dword ptr [{a['prep_done']:#x}], eax
        mov dword ptr [{a['apply_result']:#x}], eax
        mov edi, {q:#x}
        mov ecx, {QMAX * 4}
        cld
        rep stosd
        mov dword ptr [{a['sp_state']:#x}], eax
        ret
    ''')

    sendtest = put('sendtest', f'''
        mov ecx, dword ptr [{a['test_n']:#x}]
        mov dword ptr [{a['test_n']:#x}], 0
        mov edi, ecx
        mov esi, dword ptr [{a['test_seq']:#x}]
    ts_loop:
        test ecx, ecx
        je ts_out
        push ecx
        mov eax, dword ptr [{a['test_seq']:#x}]
        mov dword ptr [{a['testbody']:#x}], eax
        mov eax, dword ptr [0x5fd8c4]
        mov dword ptr [{a['testbody'] + 4:#x}], eax
        mov eax, {TEST_MSG:#x}
        mov edx, {a['testbody']:#x}
        mov ebx, 8
        call 0x519960
        inc dword ptr [{a['test_seq']:#x}]
        pop ecx
        dec ecx
        jmp ts_loop
    ts_out:
{log(K_TEST, a='edi', b='esi')}
        ret
    ''')

    turnstart = f'''
        cmp dword ptr [{a['sp_state']:#x}], 0
        jne s_nosnap
        cmp dword ptr [0x5a291c], 0
        jne s_nosnap
        mov eax, dword ptr [0x5a2918]
        cmp eax, dword ptr [{a['snap_turn']:#x}]
        je s_nosnap
        mov dword ptr [{a['snap_turn']:#x}], eax
        call {ownsave:#x}
        cmp dword ptr [0x5fd978], 1
        jne s_nosnap
        mov al, byte ptr [0x5a2b28]
        mov byte ptr [0x5a2998], al
        mov eax, -0xd
        call 0x438630
        mov eax, dword ptr [0x5a2918]
        mov dword ptr [{a['ts_turn']:#x}], eax''' if snapshot else ''
    step = put('step', f'''
{turnstart}
    s_nosnap:
        mov eax, dword ptr [{a['sp_state']:#x}]
        cmp eax, 2
        jb s_guard
        cmp eax, 4
        ja s_guard
        mov dword ptr [{a['rs_guard']:#x}], 1
    s_guard:
        cmp dword ptr [{a['test_n']:#x}], 0
        je s_state
        call {sendtest:#x}
    s_state:
        mov eax, dword ptr [{a['sp_state']:#x}]
        cmp eax, 1
        je s_prep
        cmp eax, 3
        je {send:#x}
        cmp eax, 4
        je {drain:#x}
        cmp eax, 5
        je {done:#x}
        ret
    s_prep:
        cmp dword ptr [{a['prep_done']:#x}], 0
        jne s_ret
        mov dword ptr [{a['prep_done']:#x}], 1
        jmp {prepare:#x}
    s_ret:
        ret
    ''')

    top = put('looptop', f'''
        pushad
        pushfd
        call {step:#x}
        popfd
        popad
        push esi
        push esi
        push esi
        push esi
        push ebx
        jmp 0x402206
    ''')
    p.patch(0x402201, '5656565653', jmp_rel(0x402201, top))

    p.write(a['snap_turn'], struct.pack('<ii', -1, -1))       # snap_turn, ts_turn
    out['code_end'] = code
    return {'fields': a, 'code': out}
