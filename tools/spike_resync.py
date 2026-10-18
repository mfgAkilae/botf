"""Resync spike (test build only), docs/resync_design_draft.md section 7.

A small state machine, driven by the test tool (tools/spike.py) through poke-able fields, transfers the host's
game state to every client with the stock messages 0x89 (wait dialog) and 0x72 (save file) and applies it without
closing the DirectPlay transport. No protocol: the tool copies the expected length/CRC32 from the host into the
clients and writes the states.

  sp_state  0 IDLE, 1 PREPARE (host), 2 ARMED (all), 3 SEND (host), 4 DRAIN, 5 DONE

Automatic mode (no tool needed; the manual states above still work): a heartbeat mismatch (0x5100c9, 0x51031f) no
longer shows the stock synchronization error but sets sp_detect. The host then runs PREPARE from its loop-top step,
broadcasts ARM (message 0x8a: epoch, sp_len, sp_crc) and goes on to ARMED and SEND; every other machine takes ARM
in the dispatcher head (before the mute filter) as ARMED with the host's length and CRC32, and the existing queue,
DRAIN and apply path loads the host's save. A client that sees no ARM within 120 s falls back to the stock error at
its next mismatch; after DONE the mismatches of the loaded turn are ignored (quiet window, finding B).

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
    # automatic mode
    'sp_detect': 0x2b4,    # a mismatch was seen and waits for a transfer (cleared at DONE and at the fallback)
    'sp_detect_tick': 0x2b8,  # timeGetTime of the first mismatch of that detection
    'sp_quiet': 0x2bc,     # turn of the last DONE: its mismatches are stale (finding B); -1 = none
    'sp_epoch': 0x2c0,     # host: epoch of the last ARM sent; client: of the last ARM accepted
    'sp_arm_rx': 0x2c4,    # ARMs accepted
    'sp_auto_n': 0x2c8,    # automatic transfers started (host: ARM sent)
    'sp_fallback': 0x2cc,  # 1: the next mismatch shows the stock error
    'sp_auto': 0x2d0,      # host: 1 automatic PREPARE running, 2 ARM sent
    'sp_retry': 0x2d4,     # host: the automatic PREPARE of this detection failed once
    'arm_auto': 0x2d8,     # client: this transfer was armed by an ARM message
    'arm_tick': 0x2dc,     # client: timeGetTime of that ARM
    'cnt_mismatch': 0x2e0,  # mismatches that reached the hooks (every action, see K_DETECT)
    'armbody': 0x2e4,      # 0xc: the ARM body sent (host)
    'armrx': 0x2f0,        # 0x10: body of the last ARM received
    'logring': 0x300,      # 128 x 32: (n, kind, a, b, c, d, e, f)
    'rxring': 0x1300,      # 256 x 12: (wParam, lParam, type) of every received 0x400
    'trxring': 0x1f00,     # 256 x 8: (wParam, seq) of every received test message
    'cnt_dipl': 0x2700,    # per-turn UI rebuilt after a load (finding F: diplomacy items, task-force panel)
    'ownflag': 0x2800,     # MAXSYS bytes: system i belonged to the local empire at the snapshot
    'ownbuf': 0x2a00,      # MAXSYS x 0x28: system +0x80..+0xa7 (current and last production record)
}
MAXSYS = 512
DATA_SIZE = 0x2a00 + MAXSYS * 0x28
LOG_N, RX_N, TRX_N = 128, 256, 256
QMAX = 4
TEST_MSG = 0x94            # not a stock id and not one of the planned resync ids 0x8a..0x93
# Automatic mode. 0x8a is not a stock id (ids above 0x89 end at 0x50a891 -> 0x50a73e: not handled, record left in
# the pool); the protocol table (design section 3.1) gives 0x8a to REQ, the protocol has to renumber.
ARM_MSG, ARM_LEN, ARMRX_MAX = 0x8a, 12, 0x10
FALLBACK_MS = 120000       # client: no ARM this long after its mismatch -> the next mismatch shows the stock error
ARM_WAIT_MS = 300000       # client: ARMED by an ARM and nothing from the host this long -> DONE (host failed at SEND)

# log kinds
K_PREP, K_SENT, K_QUEUED, K_REDISP, K_RETIRE, K_RAW, K_APPLY, K_FAIL, K_DONE, K_TEST = range(1, 11)
# automatic mode
#   K_DETECT   (site, turn, empire of the entry/sender, action DET_*, sp_state, sp_quiet)
#   K_AUTO     host starts PREPARE (turn, sp_retry, sp_detect_tick, [0x5a291c])
#   K_ARM      host sent ARM (epoch, len, crc, turn, send result)
#   K_ARMRX    client accepted ARM (epoch, len, crc, sender, previous sp_state, sp_detect)
#   K_ARMIGN   ARM ignored (reason IGN_*, value, sender, sp_epoch)
#   K_FALLBACK (reason FB_*, ms since the mismatch or 0, turn)
K_DETECT, K_AUTO, K_ARM, K_ARMRX, K_ARMIGN, K_FALLBACK = range(11, 17)
DET_NEW, DET_PENDING, DET_QUIET, DET_TRANSFER, DET_STOCK = range(5)
IGN_LEN, IGN_SENDER, IGN_HOST, IGN_STALE, IGN_STATE, IGN_NOGAME = range(1, 7)
FB_NOARM, FB_PREPARE = 1, 2
# failure codes
F_RAWLEN, F_RAWCRC, F_OVERFLOW, F_FLAG, F_FILE, F_TOKEN, F_RETIRE, F_ARMWAIT = range(1, 9)


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
    # After a successful apply (finding F): the screens keep per-turn caches with raw pointers into data the load freed - the diplomacy
    # screen's item lists [0x5cb510..0x5cb51c] point to order bodies (FUN_004c5340 & co.; a later click copied
    # 0x48c bytes from a freed body in FUN_004c81f0, access violation 0x4c820b) and the galaxy map's task-force
    # panel ([[0x595554]+0x7c]+0x30) into the freed task-force array. The stock load rebuilds them only at game
    # start (FUN_004b9570 returns at 0x4b9582 in a running game). Run the stock per-turn UI refresh of the turn
    # end (FUN_004b8c20, called at 0x458576: system screen, galaxy map, diplomacy rebuild FUN_004c3e40,
    # turn-results window, re-show of the current screen) after closing an open proposal panel (FUN_004c8290,
    # as FUN_004c25e0 does first). Both take no register arguments; every machine runs it after its apply.
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
        cmp dword ptr [0x592c78], 1
        jne h_ui_done
        cmp dword ptr [0x5940ac], 0
        je h_ui_done
        cmp dword ptr [0x5cb510], 0
        je h_ui_done
        cmp dword ptr [0x5cb514], 0
        je h_ui_done
        cmp dword ptr [0x5cb518], 0
        je h_ui_done
        cmp dword ptr [0x5cb51c], 0
        je h_ui_done
        cmp dword ptr [0x595554], 0
        je h_ui_done
        cmp dword ptr [0x595da8], 0
        je h_ui_done
        cmp dword ptr [0x5968a0], 0
        je h_ui_done
        call 0x4c8290
        call 0x4b8c20
        inc dword ptr [{a['cnt_dipl']:#x}]
    h_ui_done:
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

    # ---- automatic mode: host test, eax = 1 on the host ---------------------------------------------------
    # Multiplayer [0x5a2924], session [0x5a2920] and the transport role [0x5fd978] == 1 (the DirectPlay session
    # host). Not [0x5a2990]: a lobby-resumed game has it set on every machine (live run: all five started a
    # transfer); only a load corrects it (the apply helper copies it from [0x5fd978]).
    ishost = put('ishost', '''
        xor eax, eax
        cmp dword ptr [0x5a2924], 0
        je ih_out
        cmp dword ptr [0x5a2920], 0
        je ih_out
        cmp dword ptr [0x5fd978], 1
        jne ih_out
        inc eax
    ih_out:
        ret
    ''')

    # ---- automatic mode: ARM in the dispatcher head 0x50a6ef, before the mute filter ---------------------------
    # FUN_00510600 (0x50a6ef) drops a message when the receiver's local [0x5a2b50] marks its own or the sender's
    # empire; after a divergence that mask can be wrong, so the control is decoded first (design section 3.3).
    # Regs: eax = esi = wParam (sender id), edi = ebx = lParam, ecx = window message, [esp] = scratch dword (the
    # frame of 0x50a709, so 0x50a762 returns 1). The type lookup FUN_00519920 (eax = lParam, edx = wParam, as
    # 0x50a74f/0x50a704 do for 0x400) only reads the record; it needs the receive list [0x5a0dfc] (FUN_0051b150).
    # ARM changes states only, at any depth. Its record is released exactly once: FUN_00519900 copies the body
    # and frees the record (0x54dc90 -> FUN_0054dcd0); a body larger than armrx goes to a buffer of the 0x72
    # receiver's kind (FUN_00492f90, freed with FUN_00492e60; if that allocation fails the record stays in the pool
    # like a stock unknown id). Every other message runs the filter as before.
    ctl = put('ctl', f'''
        cmp ecx, 0x400
        jne c_filter
        cmp dword ptr [0x5a0dfc], 0
        je c_filter
        pushad
        mov eax, edi
        mov edx, esi
        call 0x519920
        cmp ax, {ARM_MSG:#x}
        je c_arm
        popad
    c_filter:
        call 0x510600
        jmp 0x50a6f4
    c_arm:
        mov edx, dword ptr [{a['rx_n']:#x}]
        and edx, {RX_N - 1}
        lea edx, [edx + edx*2]
        shl edx, 2
        mov dword ptr [edx + {a['rxring']:#x}], esi
        mov dword ptr [edx + {a['rxring'] + 4:#x}], edi
        mov dword ptr [edx + {a['rxring'] + 8:#x}], {ARM_MSG:#x}
        inc dword ptr [{a['rx_n']:#x}]
        mov eax, edi
        mov edx, esi
        call 0x519910
        mov ebp, eax
        cmp eax, {ARMRX_MAX}
        ja c_big
        mov eax, edi
        mov edx, {a['armrx']:#x}
        mov ebx, esi
        call 0x519900
        mov ebx, ebp
        mov ecx, {IGN_LEN}
        cmp ebp, {ARM_LEN}
        jne c_ignore
        mov ecx, {IGN_NOGAME}
        cmp dword ptr [0x5a2924], 0
        je c_ignore
        cmp dword ptr [0x5a2920], 0
        je c_ignore
        mov eax, esi
        call 0x5105d0
        mov ebx, esi
        mov ecx, {IGN_SENDER}
        test eax, eax
        je c_ignore
        call {ishost:#x}
        mov ecx, {IGN_HOST}
        test eax, eax
        jne c_ignore
        mov ebx, dword ptr [{a['armrx']:#x}]
        mov eax, ebx
        sub eax, dword ptr [{a['sp_epoch']:#x}]
        mov ecx, {IGN_STALE}
        test eax, eax
        jle c_ignore
        mov ebx, dword ptr [{a['sp_state']:#x}]
        mov ecx, {IGN_STATE}
        test ebx, ebx
        je c_accept
        cmp ebx, 2
        jne c_ignore
        cmp dword ptr [{a['arm_auto']:#x}], 0
        je c_ignore
        cmp dword ptr [{a['q_count']:#x}], 0
        jne c_ignore
    c_accept:
        mov eax, dword ptr [{a['armrx']:#x}]
        mov dword ptr [{a['sp_epoch']:#x}], eax
        mov eax, dword ptr [{a['armrx'] + 4:#x}]
        mov dword ptr [{a['sp_len']:#x}], eax
        mov eax, dword ptr [{a['armrx'] + 8:#x}]
        mov dword ptr [{a['sp_crc']:#x}], eax
        mov dword ptr [{a['rs_guard']:#x}], 1
        mov dword ptr [{a['sp_state']:#x}], 2
        mov dword ptr [{a['arm_auto']:#x}], 1
        mov dword ptr [{a['sp_fallback']:#x}], 0
        inc dword ptr [{a['sp_arm_rx']:#x}]
        call dword ptr [0x5743fc]
        mov dword ptr [{a['arm_tick']:#x}], eax
        mov eax, dword ptr [{a['sp_epoch']:#x}]
        mov ecx, dword ptr [{a['sp_len']:#x}]
        mov edx, dword ptr [{a['sp_crc']:#x}]
        mov edi, dword ptr [{a['sp_detect']:#x}]
{log(K_ARMRX, a='eax', b='ecx', c='edx', d='esi', e='ebx', f='edi')}
        popad
        jmp 0x50a762
    c_big:
        mov eax, ebp
        call 0x492f90
        test eax, eax
        je c_kept
        mov ecx, eax
        mov edx, eax
        mov eax, edi
        mov ebx, esi
        call 0x519900
        mov eax, ecx
        call 0x492e60
    c_kept:
        mov ebx, ebp
        mov ecx, {IGN_LEN}
    c_ignore:
        mov eax, dword ptr [{a['sp_epoch']:#x}]
{log(K_ARMIGN, a='ecx', b='ebx', c='esi', d='eax')}
        popad
        jmp 0x50a762
    ''')
    p.patch(0x50a6ef, call_rel(0x50a6ef, 0x510600).hex(), jmp_rel(0x50a6ef, ctl))

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

    # ---- automatic mode: the heartbeat mismatch branches ---------------------------------------------------------
    # The stock synchronization error (string 0x4bd via FUN_0048b2e0, message box FUN_005004a4, then the fatal
    # assert loop FUN_005081b0) has exactly two entries, both `mov eax,0x4bd` and both reached by every mismatch
    # branch: 0x5100c9 in the turn-end compare loop FUN_0050ffe0 (fall-through from 0x5100c3, jne from
    # 0x5101af..0x510217) and 0x51031f in the idle compare of an incoming 0x71 FUN_00510260 (fall-through from
    # 0x510319, jne from 0x510416..0x510481). The turn asserts 0x510058 / 0x5102a1 are a different (fatal) check.
    # mmcheck: eax = site, edx = empire byte of the entry or sender -> eax = 1 show the stock error, 0 handled.
    # Order: not multiplayer -> stock; a transfer running (sp_state != 0; in 2..4 the gate above already skips
    # the turn-end loop) -> ignored, the transfer heals it; turn == sp_quiet -> ignored (stale 0x71 of the turn
    # just loaded, finding B); sp_fallback -> stock; else detection (sp_detect, first tick), logged every time.
    mmcheck = put('mmcheck', f'''
        mov ebx, eax
        mov edi, edx
        cmp dword ptr [0x5a2924], 0
        je mc_stockraw
        cmp dword ptr [0x5a2920], 0
        je mc_stockraw
        inc dword ptr [{a['cnt_mismatch']:#x}]
        mov esi, {DET_TRANSFER}
        cmp dword ptr [{a['sp_state']:#x}], 0
        jne mc_log
        mov esi, {DET_QUIET}
        mov eax, dword ptr [0x5a2918]
        cmp eax, dword ptr [{a['sp_quiet']:#x}]
        je mc_log
        mov esi, {DET_STOCK}
        cmp dword ptr [{a['sp_fallback']:#x}], 0
        jne mc_log
        mov esi, {DET_PENDING}
        cmp dword ptr [{a['sp_detect']:#x}], 0
        jne mc_log
        mov esi, {DET_NEW}
        call dword ptr [0x5743fc]
        mov dword ptr [{a['sp_detect_tick']:#x}], eax
        mov dword ptr [{a['sp_detect']:#x}], 1
    mc_log:
        mov eax, dword ptr [0x5a2918]
        mov ecx, dword ptr [{a['sp_state']:#x}]
        mov edx, dword ptr [{a['sp_quiet']:#x}]
{log(K_DETECT, a='ebx', b='eax', c='edi', d='esi', e='ecx', f='edx')}
        xor eax, eax
        cmp esi, {DET_STOCK}
        jne mc_out
        inc eax
    mc_out:
        ret
    mc_stockraw:
        mov eax, 1
        ret
    ''')
    # 0x5100c9: ebp = entry offset (empire byte at entry +0x124 = [ebp+0x5cd0e4], as the stock diagnostic at
    # 0x510159); no pushes pending. Handled -> 0x51000b, the next entry (the loop has no other side effects).
    mmturn = put('mm_turn', f'''
        pushad
        movzx edx, byte ptr [ebp + 0x5cd0e4]
        mov eax, 0x5100c9
        call {mmcheck:#x}
        test eax, eax
        popad
        jne mt_stock
        jmp 0x51000b
    mt_stock:
        mov eax, 0x4bd
        jmp 0x5100ce
    ''')
    p.patch(0x5100c9, 'b8bd040000', jmp_rel(0x5100c9, mmturn))
    # 0x51031f: body at esp+0x400, empire byte at esp+0x524 (+0x20 after pushad); the record was consumed at
    # 0x510273. Handled -> 0x5103f8, the epilogue (the caller 0x50ad74 ignores eax).
    mm71 = put('mm_71', f'''
        pushad
        movzx edx, byte ptr [esp + 0x544]
        mov eax, 0x51031f
        call {mmcheck:#x}
        test eax, eax
        popad
        jne m7_stock
        jmp 0x5103f8
    m7_stock:
        mov eax, 0x4bd
        jmp 0x510324
    ''')
    p.patch(0x51031f, 'b8bd040000', jmp_rel(0x51031f, mm71))

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

    # Automatic mode at DONE: sp_auto == 1 means the host's automatic PREPARE failed before ARM went out (nothing
    # was sent, the clients still wait with sp_detect): keep sp_detect for one retry from the next loop-top step;
    # a second failure gives up and lets the next mismatch show the stock error. Every other DONE (also a manual
    # transfer, a rejected file or an ARMED timeout) opens the quiet window for the current turn: a machine that
    # was still in its turn processing sends its 0x71 of this turn after the others loaded, and their idle compare
    # takes it for a mismatch (finding B). A genuine 0x71 after the load follows the sender's next turn
    # processing, which increments the turn (0x45856b) before the send (0x50ffec), so it never carries the loaded
    # turn; the loop-top step closes the window as soon as the turn changes.
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
        cmp dword ptr [{a['sp_auto']:#x}], 1
        jne dn_quiet
        cmp dword ptr [{a['sp_retry']:#x}], 0
        jne dn_giveup
        mov dword ptr [{a['sp_retry']:#x}], 1
        jmp dn_out
    dn_giveup:
        mov dword ptr [{a['sp_retry']:#x}], eax
        mov dword ptr [{a['sp_detect']:#x}], eax
        mov dword ptr [{a['sp_fallback']:#x}], 1
        mov ecx, dword ptr [0x5a2918]
{log(K_FALLBACK, a=FB_PREPARE, b=0, c='ecx')}
        jmp dn_out
    dn_quiet:
        mov ecx, dword ptr [0x5a2918]
        mov dword ptr [{a['sp_quiet']:#x}], ecx
        mov dword ptr [{a['sp_detect']:#x}], eax
        mov dword ptr [{a['sp_retry']:#x}], eax
    dn_out:
        mov dword ptr [{a['sp_auto']:#x}], eax
        mov dword ptr [{a['arm_auto']:#x}], eax
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

    # ---- automatic mode: ARM after a successful automatic PREPARE (host) ---------------------------------------
    # PREPARE leaves sp_state at 1 on success and sets 5 on failure. ARM goes out before 0x89 and 0x72 from the
    # same sender, so per-sender in-order delivery (spike section 7.1) dispatches it first on every client.
    arm = put('arm', f'''
        cmp dword ptr [{a['sp_state']:#x}], 1
        jne ar_out
        inc dword ptr [{a['sp_epoch']:#x}]
        mov eax, dword ptr [{a['sp_epoch']:#x}]
        mov dword ptr [{a['armbody']:#x}], eax
        mov eax, dword ptr [{a['sp_len']:#x}]
        mov dword ptr [{a['armbody'] + 4:#x}], eax
        mov eax, dword ptr [{a['sp_crc']:#x}]
        mov dword ptr [{a['armbody'] + 8:#x}], eax
        mov eax, {ARM_MSG:#x}
        mov edx, {a['armbody']:#x}
        mov ebx, {ARM_LEN}
        call 0x519960
        mov esi, eax
        inc dword ptr [{a['sp_auto_n']:#x}]
        mov dword ptr [{a['sp_auto']:#x}], 2
        mov dword ptr [{a['rs_guard']:#x}], 1
        mov dword ptr [{a['sp_state']:#x}], 2
        mov eax, dword ptr [{a['sp_epoch']:#x}]
        mov ecx, dword ptr [{a['sp_len']:#x}]
        mov edx, dword ptr [{a['sp_crc']:#x}]
        mov ebx, dword ptr [0x5a2918]
{log(K_ARM, a='eax', b='ecx', c='edx', d='ebx', e='esi')}
    ar_out:
        ret
    ''')

    # ---- automatic mode: loop-top part (runs before the state switch) -------------------------------------------
    # 1. the quiet window ends when the turn changes (also keeps a later game of this process at the same turn
    #    number unaffected);
    # 2. client ARMED by an ARM and nothing queued for ARM_WAIT_MS: the host failed between ARM and SEND (its SEND
    #    checks the file before 0x89 goes out) -> DONE without an apply; no dialog is open in state 2;
    # 3. host: ARM went out in an earlier step -> SEND (the driver's step 3);
    # 4. idle with sp_detect: the host starts PREPARE unless it is in its turn processing ([0x5a291c] == 1); a
    #    client waits for ARM and after FALLBACK_MS lets its next mismatch show the stock error.
    auto = put('autostep', f'''
        mov eax, dword ptr [{a['sp_quiet']:#x}]
        cmp eax, -1
        je au_wait
        cmp eax, dword ptr [0x5a2918]
        je au_wait
        mov dword ptr [{a['sp_quiet']:#x}], -1
    au_wait:
        cmp dword ptr [{a['arm_auto']:#x}], 0
        je au_host
        cmp dword ptr [{a['sp_state']:#x}], 2
        jne au_host
        cmp dword ptr [{a['q_count']:#x}], 0
        jne au_host
        call dword ptr [0x5743fc]
        sub eax, dword ptr [{a['arm_tick']:#x}]
        cmp eax, {ARM_WAIT_MS}
        jb au_host
        mov ebx, eax
        mov dword ptr [{a['last_fail']:#x}], {F_ARMWAIT}
{log(K_FAIL, a=F_ARMWAIT, b='ebx')}
        mov dword ptr [{a['apply_result']:#x}], 2
        mov dword ptr [{a['sp_state']:#x}], 5
        ret
    au_host:
        mov eax, dword ptr [{a['sp_state']:#x}]
        cmp eax, 2
        jne au_idle
        cmp dword ptr [{a['sp_auto']:#x}], 2
        jne au_ret
        mov dword ptr [{a['sp_state']:#x}], 3
        ret
    au_idle:
        test eax, eax
        jne au_ret
        cmp dword ptr [{a['sp_detect']:#x}], 0
        je au_ret
        call {ishost:#x}
        test eax, eax
        je au_client
        cmp dword ptr [0x5a291c], 1
        je au_ret
        mov dword ptr [{a['sp_auto']:#x}], 1
        mov dword ptr [{a['prep_done']:#x}], 0
        mov dword ptr [{a['sp_state']:#x}], 1
        mov eax, dword ptr [0x5a2918]
        mov ecx, dword ptr [{a['sp_retry']:#x}]
        mov edx, dword ptr [{a['sp_detect_tick']:#x}]
        mov ebx, dword ptr [0x5a291c]
{log(K_AUTO, a='eax', b='ecx', c='edx', d='ebx')}
        ret
    au_client:
        call dword ptr [0x5743fc]
        sub eax, dword ptr [{a['sp_detect_tick']:#x}]
        cmp eax, {FALLBACK_MS}
        jb au_ret
        mov dword ptr [{a['sp_fallback']:#x}], 1
        mov dword ptr [{a['sp_detect']:#x}], 0
        mov ecx, dword ptr [0x5a2918]
{log(K_FALLBACK, a=FB_NOARM, b='eax', c='ecx')}
    au_ret:
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
        je s_auto
        call {sendtest:#x}
    s_auto:
        call {auto:#x}
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
        cmp dword ptr [{a['sp_auto']:#x}], 0
        je {prepare:#x}
        call {prepare:#x}
        jmp {arm:#x}
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
    p.write(a['sp_quiet'], struct.pack('<i', -1))
    out['code_end'] = code
    return {'fields': a, 'code': out}
