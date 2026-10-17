"""BotF multiplayer network/desync fix for trek.exe (vanilla 2.0.4 English/German builds).

Fix A  End-of-turn message order: send the production queues (msg 0x74) BEFORE the orders
       (msg 0x68). The 0x68 handler on the other machines starts turn processing as soon as the
       last player's orders arrive; queues sent afterwards were applied in the middle of (or after)
       turn processing -> remote machines produced with stale build queues -> desync.
Fix B  While a machine is processing a turn (busy flag 0x5a291c == 1) incoming 0x68/0x74
       (orders / queues of a faster player for the NEXT turn) are no longer applied in the middle
       of turn processing (the turn code pumps messages). Their notifications are parked and
       re-posted, in order, once processing has finished.
Fix C  DPMP send loop (dpmppckt.c): the network critical section was held for the whole message
       including a Sleep(10) per 466-byte packet and synchronous guaranteed sends (one ack round
       trip each); the receive thread was blocked meanwhile. Now the lock only covers the shared
       sequence counters, the per-packet Sleep is 0, and a failing IDirectPlay::Send is retried
       for ~5 s instead of forever (an endless retry froze the game when a peer was gone).

Fix D  Keepalive: the receive thread now wakes every 10 s and sends a 1-byte unreliable message
       to all players (ignored by every receiver, patched or not). Late-game turn calculations
       can take minutes without any game traffic; idle UDP mappings in NAT routers/firewalls
       expire and DirectPlay only starts pinging after 35 s of silence (and only towards the
       host), after which unanswered pings drop the player ("Disconnected" / host migration).

Fix I  Martial law (production action 7) counts its turns in the word at system+0x86. When the
       owner removes martial law from the head of a build queue, its own UI kill (mode 1) leaves the
       record alone and the new selection writes +0x86 = 0; the other machines execute the kill
       request (mode 2), which resets +0x80..+0x99 but only the WORD at +0x84, so +0x86 keeps the
       old count. After re-selecting martial law the other machines reach the race threshold
       earlier and raise the system's morale (+0x2dc, inside the heartbeat crcSolarBld) one or more
       turns before the owner: "A synchronization error has occurred", same seed, only crcSolarBld
       differs (reproduced on the original exe with 5 players, turn 105). The mode-2 reset now
       clears the dword +0x84..+0x87.

Fix M  Production orders that the owner creates during turn processing (queue advance, re-arm)
       exist only on the owner until its next end-of-turn message. When the owner deletes such a
       build in the following turn, its kill request (type 9, target seqno only) finds nothing on
       the other machines ("Failed to Kill order"), so they skip the production reset and keep the
       old build's invested industry; the replacement build then gets that industry on every machine
       except the owner and completes earlier there -> crcSolarBld-only sync error (reproduced on the
       original with 5 players: delete a fresh multi-turn build). The kill request now carries the
       target system in its order header (+0x0c = 0x4B4B0000 | system, transmitted with the header,
       ignored by unpatched games), and a kill request that finds no order applies the same
       production reset to that system.

Fix N  Deleting a build that was BOUGHT (queue screen, "delete current build?" -> YES, FUN_004fd7b8)
       removes the buy order (production order sub-kind 1) only on the owner's machine: the code
       calls the local kill (mode 1) but, unlike every other delete path, sends no kill request.
       The other machines keep the buy order and charge/complete the purchase later, so the
       system's build cost total (+0x2c2, inside crcSolarBld) differs -> sync error. Found by a
       natural 5-player test game on the original (turn 331) and reproduced from its turn-320 save.
       The delete path now sends the kill request like the others.

All changes keep the wire format (packet size, header, message ids) unchanged, so patched and
unpatched peers can still connect; the fixes take full effect when every player is patched.
"""
import struct
from asmutil import asm, call_rel, jmp_rel

IAT_ENTER = 0x5744ac
IAT_LEAVE = 0x574548
IAT_SLEEP = 0x574594
IAT_POSTMSG = 0x57462c
NET_HWND = 0x5a074c        # window that receives 0x400 network notifications
BUSY = 0x5a291c            # 1 = turn processing, -1 = waiting for others, 0 = idle
NETCS = 0x688600           # DPMP critical section
SEND_PACKET = 0x54bc10     # IDirectPlay::Send wrapper, returns 1 on success
IAT_WFSO = 0x5745c0
IAT_TIMEGETTIME = 0x5743fc
IDPLAY = 0x5a0730          # IDirectPlay3A*
SESSION_OPEN = 0x5fd97c
LOCAL_DPID = 0x5fd8c4
RX_RUNNING = 0x5a0748      # receive thread run flag
KEEPALIVE_MS = 10000
MAX_DEFER = 24
SEND_TRIES = 250           # x 20 ms

# Code goes into an unused, zero-filled area of the code section (0x516e5c..0x517e00, zero in all
# 134 trek.exe builds shipped with the 2.0.4 installer); mutable data into the unused tail of
# .bss (last variable referenced anywhere is 0x6896d4, the section ends at 0x689800).
CODE_CAVE, CODE_CAVE_END = 0x516e60, 0x517e00
DATA_CAVE, DATA_CAVE_END = 0x6896e0, 0x689800
# More mutable data (the .bss tail is full): the end of DGROUP. Its file data ends at 0x5a1600 (last non-zero byte
# 0x5a142d) and the loader maps the section up to 0x5a2000 zero-filled; nothing in the 8 installer variants refers
# to 0x5a1500..0x5a2000, and the area stays zero during play.
DATA2, DATA2_END = 0x5a1600, 0x5a2000


def apply(p):
    data = DATA_CAVE
    d_fail = data + 0x00
    d_count = data + 0x04
    # +0x08 keepalive byte, +0x0c last keepalive time (see Fix D)
    d_arr = data + 0x10                      # MAX_DEFER * (wParam, lParam)
    assert d_arr + MAX_DEFER * 8 <= DATA_CAVE_END
    if any(p.read(CODE_CAVE, CODE_CAVE_END - CODE_CAVE)):
        raise ValueError('code cave 0x516e60 is not free in this trek.exe')
    code = CODE_CAVE
    out = {}

    def put(name, text):
        nonlocal code
        b = asm(text, code)
        assert code + len(b) <= CODE_CAVE_END
        p.write(code, b)
        out[name] = code
        code += (len(b) + 15) & ~15
        return out[name]

    # ---- flush parked notifications (pushad-safe helper, stdcall-free) -----------------
    flush = put('flush', f'''
        pushad
        xor esi, esi
    loop_:
        cmp esi, dword ptr [{d_count:#x}]
        jae done
        mov eax, dword ptr [{d_arr:#x} + esi*8 + 4]
        push eax
        mov eax, dword ptr [{d_arr:#x} + esi*8]
        push eax
        push 0x400
        push dword ptr [{NET_HWND:#x}]
        call dword ptr [{IAT_POSTMSG:#x}]
        inc esi
        jmp loop_
    done:
        mov dword ptr [{d_count:#x}], 0
        popad
        ret
    ''')

    # ---- Fix B: dispatcher hook at 0x50a709 (after the message id lookup) -------------
    # regs here: AX = message id, ECX = window message, ESI = wParam, EDI = lParam
    disp = put('dispatch', f'''
        mov word ptr [esp], ax
        mov eax, dword ptr [esp]
        cmp ecx, 0x400
        jne go
        cmp dword ptr [{BUSY:#x}], 1
        je busy
        cmp dword ptr [{d_count:#x}], 0
        je go
        call park
        call {flush:#x}
        jmp skip
    busy:
        cmp ax, 0x68
        je park_it
        cmp ax, 0x74
        je park_it
        cmp ax, 0x85
        je park_it
        cmp ax, 0x72
        je park_it
        cmp ax, 0x73
        je park_it
        jmp go
    park_it:
        cmp dword ptr [{d_count:#x}], {MAX_DEFER - 1}
        jae go
        call park
    skip:
        jmp 0x50a762
    go:
        jmp 0x50a710
    park:
        push eax
        mov eax, dword ptr [{d_count:#x}]
        mov dword ptr [{d_arr:#x} + eax*8], esi
        mov dword ptr [{d_arr:#x} + eax*8 + 4], edi
        inc dword ptr [{d_count:#x}]
        pop eax
        ret
    ''')
    p.patch(0x50a709, '668904248b0424', jmp_rel(0x50a709, disp) + b'\x90\x90')

    # ---- Fix B: re-post parked notifications when turn processing ends (0x4586d6) -------
    endturn = put('endturn', f'''
        mov dword ptr [{BUSY:#x}], 0
        call {flush:#x}
        xor edi, edi
        ret
    ''')
    p.patch(0x4586d6, '31ff893d1c295a00', call_rel(0x4586d6, endturn) + b'\x90\x90\x90')

    # ---- Fix A: send production queues (0x74) before orders (0x68) ----------------------
    p.patch(0x458155, call_rel(0x458155, 0x456340), call_rel(0x458155, 0x44d580))
    p.patch(0x45815a, call_rel(0x45815a, 0x44d580), call_rel(0x45815a, 0x456340))

    # ---- Fix C: send loop locking ---------------------------------------------------------
    # 0x54e042: after the shared counters were read -> leave the critical section
    unlock = put('unlock', f'''
        mov dword ptr [esp+0x34], edx
        mov dword ptr [esp+0x28], eax
        pushad
        push {NETCS:#x}
        call dword ptr [{IAT_LEAVE:#x}]
        popad
        mov dword ptr [{d_fail:#x}], 0
        jmp 0x54e04a
    ''')
    p.patch(0x54e042, '8954243489442428', jmp_rel(0x54e042, unlock) + b'\x90\x90\x90')
    # 0x54e1f4: re-enter before the counters are incremented (original code leaves it after)
    relock = put('relock', f'''
        pushad
        push {NETCS:#x}
        call dword ptr [{IAT_ENTER:#x}]
        popad
        push {NETCS:#x}
        jmp 0x54e1f9
    ''')
    p.patch(0x54e1f4, '6800866800', jmp_rel(0x54e1f4, relock))
    # bounded retry instead of an endless loop around IDirectPlay::Send
    send = put('send', f'''
        cmp dword ptr [{d_fail:#x}], 0
        jne give_up
        push esi
        mov esi, {SEND_TRIES}
    try_:
        push eax
        push edx
        push ebx
        push ecx
        call {SEND_PACKET:#x}
        cmp eax, 1
        je ok
        dec esi
        jz fail
        push 20
        call dword ptr [{IAT_SLEEP:#x}]
        pop ecx
        pop ebx
        pop edx
        pop eax
        jmp try_
    ok:
        add esp, 16
        pop esi
        mov eax, 1
        ret
    fail:
        add esp, 16
        pop esi
        mov dword ptr [{d_fail:#x}], 1
    give_up:
        mov eax, 1
        ret
    ''')
    p.patch(0x54e172, call_rel(0x54e172, SEND_PACKET), call_rel(0x54e172, send))
    # no artificial 10 ms pause per packet
    if p.read(0x54e1cd, 2) != bytes.fromhex('6a00'):   # community packet.patch already sets 0
        p.patch(0x54e1cd, '6a0a', '6a00')

    # ---- Fix D: application keepalive from the receive thread ------------------------------
    # The receive thread waited INFINITE for DirectPlay's message event. Now it wakes up every
    # 10 s and sends a 1-byte non-guaranteed message to all players. Receivers (patched or not)
    # drop messages shorter than 4 bytes before the game sees them (0x54da49). This keeps the
    # link (and NAT/firewall mappings) alive while a machine sits in a long turn calculation.
    ka_byte = data + 0x08      # payload of the keepalive message (zero-initialised .bss)
    d_lastka = data + 0x0c
    keepalive = put('keepalive', f'''
        pushad
        mov eax, dword ptr [{IDPLAY:#x}]
        test eax, eax
        jz done
        cmp dword ptr [{SESSION_OPEN:#x}], 0
        je done
        push 1
        push {ka_byte:#x}
        push 0
        push 0
        push dword ptr [{LOCAL_DPID:#x}]
        push eax
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x68]
    done:
        popad
        ret
    ''')
    # time based: every wake-up (message or 1 s timeout) checks whether 10 s have passed since
    # the last keepalive, so each side sends regardless of how much it receives
    rxwait = put('rxwait', f'''
    wait_:
        cmp dword ptr [{RX_RUNNING:#x}], 1
        jne skipka
        pushad
        call dword ptr [{IAT_TIMEGETTIME:#x}]
        mov edx, eax
        sub edx, dword ptr [{d_lastka:#x}]
        cmp edx, {KEEPALIVE_MS}
        jb noka
        mov dword ptr [{d_lastka:#x}], eax
        call {keepalive:#x}
    noka:
        popad
    skipka:
        push 1000
        push edi
        call dword ptr [{IAT_WFSO:#x}]
        cmp eax, 0x102
        jne got
        cmp dword ptr [{RX_RUNNING:#x}], 1
        jne quit
        jmp wait_
    got:
        jmp 0x54db24
    quit:
        jmp 0x54db2d
    ''')
    # 0x54db13: push -1 / push edi / call [WaitForSingleObject] / cmp eax,0x102 / jz  (17 bytes)
    p.patch(0x54db13, '6aff572eff15c04557003d020100007409', jmp_rel(0x54db13, rxwait) + b'\x90' * 12)
    # the receive loop jumps back to 0x54db13 after each batch -> lands on our wait loop

    # ---- Fix E: no "kill order" requests from deterministic turn processing --------------------
    # Orders carry a sequence number from per-empire counters (0x590230..0x590244). The counters
    # are machine local and drift apart (UI code creates search orders all the time), so the same
    # logical order has different numbers on different machines. FUN_00457940 creates a type-9
    # "kill request" (payload = the target's LOCAL sequence number) that is sent with the next
    # orders message; every other machine executes it at the start of its next turn by matching
    # the sequence number only (FUN_00457890 -> FUN_004576c4 mode 2 -> matcher 0x457b50).
    # Turn processing itself calls FUN_00457940 (e.g. FUN_00466468) and then kills the target
    # locally; every machine runs the same code, so the request is redundant - but on the
    # receivers its number can belong to a different live order (minor race / own orders), which
    # then gets killed on that machine only -> desync, more likely the more orders a game has.
    # Requests are now only created outside turn processing (player actions, also while a
    # nested message pump runs inside the turn).
    d_depth = data + 0xd0       # DispatchMessage nesting depth
    d_depth0 = data + 0xd4      # depth when turn processing started
    assert d_depth0 + 4 <= DATA_CAVE_END
    dwrap = put('dispatchwrap', f'''
        inc dword ptr [{d_depth:#x}]
        push dword ptr [esp+4]
        call dword ptr [0x5745ec]
        dec dword ptr [{d_depth:#x}]
        ret 4
    ''')
    for site in (0x402232, 0x4023ca, 0x402509):
        p.patch(site, '2eff15ec455700', call_rel(site, dwrap) + b'\x90\x90')
    d_proddone = data + 0x11c   # Fix H: 1 once this turn's production step ran (cleared at turn start)
    pstart = put('pstart', f'''
        mov dword ptr [{BUSY:#x}], 1
        mov dword ptr [{d_proddone:#x}], 0
        push eax
        mov eax, dword ptr [{d_depth:#x}]
        mov dword ptr [{d_depth0:#x}], eax
        pop eax
        ret
    ''')
    p.patch(0x458215, 'c7051c295a0001000000', call_rel(0x458215, pstart) + b'\x90' * 5)
    krq = put('killreq', f'''
        mov ecx, dword ptr [0x5a2924]
        cmp dword ptr [{BUSY:#x}], 1
        jne done
        push eax
        mov eax, dword ptr [{d_depth:#x}]
        cmp eax, dword ptr [{d_depth0:#x}]
        pop eax
        jne done
        xor ecx, ecx
    done:
        ret
    ''')
    # 0x457946: mov ecx,[MP flag]; the following test ecx,ecx / jnz skips the request when 0
    p.patch(0x457946, '8b0d24295a00', call_rel(0x457946, krq) + b'\x90')

    # ---- Fix I: mode-2 production reset also clears the martial-law turn counter +0x86 ----------
    # original 0x45774a..0x457786 (EDX = system index * 0x328, EAX = system array base):
    #   mov word [edx+eax+0x84],0 / mov dword [edx+eax+0x80],0 / mov word [edx+eax+0x88],0x7fff /
    #   mov word [edx+eax+0x8a],0x7fff / mov word [edx+eax+0x90],0xffff / mov word [edx+eax+0x98],0
    # EDX and EAX are reloaded right after (0x457787 / 0x45778e).
    old_i = ('66c78402840000000000' 'c784028000000000000000' '66c7840288000000ff7f'
             '66c784028a000000ff7f' '66c7840290000000ffff' '66c78402980000000000')
    new_i = asm('''
        add edx, eax
        mov dword ptr [edx+0x80], 0
        mov dword ptr [edx+0x84], 0
        mov dword ptr [edx+0x88], 0x7fff7fff
        mov word ptr [edx+0x90], 0xffff
        mov word ptr [edx+0x98], 0
    ''', 0x45774a)
    assert len(new_i) <= 61
    p.patch(0x45774a, old_i, new_i + bytes([0x90]) * (61 - len(new_i)))

    # ---- Fix M: kill requests for production orders the receivers do not know yet -----------------
    # owner side, FUN_00457940 after the kill request (ECX) got its body: [esp+4] = target header
    killmark = put('killmark', f'''
        mov eax, dword ptr [esp+8]
        mov edx, dword ptr [ecx+0x14]
        push eax
        mov eax, dword ptr [eax]
        mov dword ptr [edx], eax
        pop eax
        cmp dword ptr [eax+0x10], 0
        jne done
        mov edx, dword ptr [eax+0x14]
        test edx, edx
        jz done
        push ebx
        mov ebx, dword ptr [edx]
        test ebx, ebx
        jz mark
        cmp ebx, 2
        jne nomark
    mark:
        movzx ebx, word ptr [edx+4]
        or ebx, 0x4b4b0000
        mov dword ptr [ecx+0xc], ebx
    nomark:
        pop ebx
    done:
        mov edx, dword ptr [ecx+0x14]
        ret
    ''')
    # 0x4579cb: mov eax,[esp+4] / mov edx,[ecx+0x14] / mov eax,[eax] / mov [edx],eax  (11 bytes)
    p.patch(0x4579cb, '8b4424048b51148b008902', call_rel(0x4579cb, killmark) + bytes([0x90]) * 6)
    # receiver side, FUN_004576c4 mode 2 "Failed to Kill order" (ECX = kill request header)
    nfreset = put('nfreset', f'''
        mov eax, dword ptr [ecx+0xc]
        mov edx, eax
        and edx, 0xffff0000
        cmp edx, 0x4b4b0000
        jne orig
        and eax, 0xffff
        cmp ax, word ptr [0x5a36bc]
        jae orig
        imul eax, eax, 0x328
        add eax, dword ptr [0x5a36c8]
        mov dword ptr [eax+0x80], 0
        mov dword ptr [eax+0x84], 0
        mov dword ptr [eax+0x88], 0x7fff7fff
        mov word ptr [eax+0x90], 0xffff
        mov word ptr [eax+0x98], 0
    orig:
        xor eax, eax
        push edi
        mov esi, dword ptr [ecx]
        push esi
        mov edi, dword ptr [ecx+4]
        jmp 0x4577e2
    ''')
    # 0x4577db: push edi / mov esi,[ecx] / push esi / mov edi,[ecx+4]  (7 bytes)
    p.patch(0x4577db, '578b31568b7904', jmp_rel(0x4577db, nfreset) + bytes([0x90]) * 2)

    # ---- Fix N: send a kill request when a bought build is deleted from the queue -------------------
    # Only the 5-byte call at 0x4fd92f is redirected (mods such as ECM/PLUS changed the bytes before it).
    # On entry EAX = buy-order search pattern, EDX = 1 (local kill of all matches).
    buydel = put('buydel', f'''
        push eax
        push edx
        cmp dword ptr [0x5a2924], 0
        je local
        call 0x457940
    local:
        pop edx
        pop eax
        jmp 0x4576c4
    ''')
    p.patch(0x4fd92f, call_rel(0x4fd92f, 0x4576c4), call_rel(0x4fd92f, buydel))

    # ---- Fix S: serialize SmartHeap's default pool (malloc/free) -------------------------------------
    # The network receive thread allocates a list node for every incoming game message with malloc
    # (0x566cb0 -> 0x51b2b0 -> 0x51d760), while the main thread uses the same pool all the time. The
    # default pool is created from the static flags at 0x5a0a1c = MEM_POOL_DEFAULT (0x8000) without
    # MEM_POOL_SERIALIZE (0x0002), so MemAllocPtr/MemFreePtr take no lock: two threads can be handed the
    # same block and the heap breaks (silent exits in the resource loader / inflate, crashes in the
    # receive thread). The game's other pools that the receive thread uses already have 0x8002.
    # With the flag MemPoolInit (0x52ef48) initializes the pool's critical section itself.
    p.patch(0x5a0a1c, '0080', '0280')

    # ---- Fix H: no owner-only production restart before the production snapshot ----------------------
    # Losing a shipyard (scrap order, bombardment, unrest) runs FUN_00445840 -> FUN_00445a10 during turn
    # processing, before the production loop. If the system was building a ship, every machine kills the
    # order and clears the record, but only the OWNER starts the next queue item again (0x445ab5:
    # FUN_0046138c, or FUN_004616f0 + FUN_0044d830). That new order is already in the production snapshot,
    # so the owner gets one turn of progress the others only get a turn later -> the owner finishes the
    # build a turn early -> sync error (crcSolarBld only). Reproduced: saves/five_1201_t103, scrap the Union
    # Shipyard at Cardassia -> mismatch at turn 106. FUN_00445840 has the same pattern for an empty queue
    # (0x4459cd). The developers already defer this for conquered systems (FUN_004618c0 list, processed by
    # FUN_00461640 after the production loop); these two paths were missed.
    # Now, in MP while busy == 1 and before this turn's production step, both restarts are queued and run right
    # after FUN_00461640 (0x46252f). Shipyard losses after the production step (sabotage, research) restart at
    # once as before: the snapshot is already taken then.
    # A deferred restart of the second kind (empty queue, any human player's system) is skipped when the system
    # no longer belongs to a human player or has no queue any more: a computer empire can conquer it later in the
    # same processing (bombardment, then invasion), which frees the queue, and FUN_0044d830 would then read through
    # a null queue pointer (0x44d84b) on every machine (review finding N8, static).
    d_rearm_n = data + 0xd8
    d_rearm = data + 0xdc                  # MAX_REARM * (word system, word kind)
    MAX_REARM = 16
    assert d_rearm + MAX_REARM * 4 <= d_proddone and d_proddone + 4 <= DATA_CAVE_END
    MP = 0x5a2924
    rearm_a = put('rearm_a', f'''
        cmp dword ptr [{MP:#x}], 0
        je orig
        cmp dword ptr [{BUSY:#x}], 1
        jne orig
        cmp dword ptr [{d_proddone:#x}], 0
        jne orig
        mov eax, dword ptr [{d_rearm_n:#x}]
        cmp eax, {MAX_REARM}
        jae orig
        mov word ptr [eax*4 + {d_rearm:#x}], cx
        mov word ptr [eax*4 + {d_rearm + 2:#x}], 0
        inc dword ptr [{d_rearm_n:#x}]
        jmp 0x445a37
    orig:
        mov eax, ecx
        call 0x44dc70
        jmp 0x445abc
    ''')
    # 0x445ab5: mov eax,ecx / call FUN_0044dc70 (7 bytes); owner == local was checked just before
    p.patch(0x445ab5, '89c8' + call_rel(0x445ab7, 0x44dc70).hex(), jmp_rel(0x445ab5, rearm_a) + b'\x90\x90')
    rearm_b = put('rearm_b', f'''
        cmp dword ptr [{MP:#x}], 0
        je orig
        cmp dword ptr [{BUSY:#x}], 1
        jne orig
        cmp dword ptr [{d_proddone:#x}], 0
        jne orig
        movzx eax, byte ptr [esi+0x4c]
        cmp eax, 5
        jae orig
        bt dword ptr [0x5a2b28], eax
        jnc orig
        mov eax, dword ptr [{d_rearm_n:#x}]
        cmp eax, {MAX_REARM}
        jae orig
        mov word ptr [eax*4 + {d_rearm:#x}], cx
        mov word ptr [eax*4 + {d_rearm + 2:#x}], 1
        inc dword ptr [{d_rearm_n:#x}]
        jmp 0x4459e1
    orig:
        mov eax, ecx
        call 0x4616f0
        jmp 0x4459d4
    ''')
    # 0x4459cd: mov eax,ecx / call FUN_004616f0 (7 bytes); ESI = system, ECX = system index
    p.patch(0x4459cd, '89c8' + call_rel(0x4459cf, 0x4616f0).hex(), jmp_rel(0x4459cd, rearm_b) + b'\x90\x90')
    rearm_run = put('rearm_run', f'''
        call 0x461640
        pushad
        xor edi, edi
    next:
        cmp edi, dword ptr [{d_rearm_n:#x}]
        jae done
        movsx ecx, word ptr [edi*4 + {d_rearm:#x}]
        imul esi, ecx, 0x328
        add esi, dword ptr [0x5a36c8]
        cmp word ptr [edi*4 + {d_rearm + 2:#x}], 0
        jne kind1
        mov al, byte ptr [esi+0x4c]
        cmp al, byte ptr [0x5a2b2a]
        jne skip
        mov eax, ecx
        call 0x44dc70
        test eax, eax
        je head
        jmp auto
    kind1:
        cmp dword ptr [esi+0xa8], 0
        je skip
        movzx eax, byte ptr [esi+0x4c]
        cmp eax, 5
        jae skip
        bt dword ptr [0x5a2b28], eax
        jnc skip
    auto:
        mov eax, ecx
        call 0x4616f0
        lea edx, [esi+0x80]
        mov eax, ecx
        call 0x44d830
        jmp skip
    head:
        mov eax, ecx
        call 0x46138c
    skip:
        inc edi
        jmp next
    done:
        mov dword ptr [{d_rearm_n:#x}], 0
        mov dword ptr [{d_proddone:#x}], 1
        popad
        ret
    ''')
    p.patch(0x46252f, call_rel(0x46252f, 0x461640), call_rel(0x46252f, rearm_run))

    # ---- Fix J: ship-class refit creates the replacement build order only on the owner's machine -------
    # When research makes a ship class obsolete, FUN_0044a360 refits the ships of that empire and, for a
    # human empire, replaces every system's build order of the old class: kill the old order (same on all
    # machines) and add a new one (0x44a4ea..0x44a4fc). The new order gets its sequence number from THIS
    # machine's counter for that empire (FUN_0045748c), and the counters differ between machines. The
    # owner sends its order with the next orders message; the other machines keep their own copy too
    # (the merge only drops equal numbers) and build twice -> sync error. Reproduced with
    # tools/r4inject.py (refit 18 -> 9 for empire 0 from saves/five_1201_t103): mismatch at turn 106.
    # The refit runs after the production loop, so nobody needs the order before the owner's copy arrives.
    refit = put('refit', f'''
        mov al, byte ptr [esp+0x130]
        cmp al, 5
        jae add
        cmp al, byte ptr [0x5a2b2a]
        jne 0x44a4fd
    add:
        mov ebx, ebp
        mov eax, ecx
        movsx edx, word ptr [esi]
        call 0x463820
        mov eax, ecx
        call 0x457b9c
        jmp 0x44a4fd
    ''')
    p.patch(0x44a4ea, '89eb89c80fbf16' + call_rel(0x44a4f1, 0x463820).hex() + '89c8' + call_rel(0x44a4f8, 0x457b9c).hex(),
            jmp_rel(0x44a4ea, refit) + b'\x90' * 14)

    # ---- Fix T: tactical combat crash "ai\assault.c line 562 entity->ship.shipData.targetIsEntity" ---------
    # Orders 7, 8 and 10 in the tactical view clear a ship's target (0x4972f7: flag +0x20c bit 3 off, target
    # +0x200 = -1). If the player then gives order 1 or 2 without picking a new target, the combat step runs
    # FUN_00567c30 (0x5543f6 dispatch), which asserts that the target is an entity before it checks for -1:
    # the game ends with Crash.log and everybody else sees "Disconnected". Found by the tactical-combat agent
    # (Romulan ship vs the Edo Guardian, turn 293). Both asserts (ship 0x567c88, monster 0x567d45) now take the
    # existing "no target" branch at 0x567d6f: the unit keeps its position for this combat round.
    for site, old in ((0x567c88, 'bb10a45800'), (0x567d45, 'bb38a45800')):     # mov ebx, <assert text>
        p.patch(site, old, jmp_rel(site, 0x567d6f))

    # ---- Fix W: monster spawn countdown is reset on new game / load ------------------------------------
    # The random-monster countdown [0x58fdb0] (FUN_0044cbe0, called every turn by the incident step) starts at
    # 0x4b when trek.exe starts and is never reset or saved. A player who restarts the game after a crash or
    # "Disconnected" has 75 while the others, who reload the save in their running game, have whatever their
    # process counted down to: monsters then appear on one machine only -> sync error (different seed).
    # Reproduced: different counters on the turn-103 save -> mismatch in the same turn. FUN_00450020 resets
    # the Borg/monster state on new game and on loading (traced on an MP client); it now resets the countdown.
    # The same function also resets two per-process monster name counters ([0x58fdd4] = 233, [0x58fddc] = 1; the
    # names are part of the ship checksum) and drops the economy-checksum scratch buffer [0x58fd20] of
    # FUN_0043db00, which is allocated once for the system count of the first game and never resized (a larger
    # galaxy loaded later in the same process overran it). It is allocated again on its next use.
    # It also resets the ship-name table 0x5b5568 (FUN_00475410, otherwise only called for a new game): the
    # number of RNG draws when naming a new ship depends on that table, so a restarted player went out of sync
    # at the first new ship after loading (found by a static code review).
    w_reset = put('monreset', f'''
        mov dword ptr [0x58fde4], edx
        mov dword ptr [0x58fdb0], 0x4b
        mov dword ptr [0x58fdd4], 233
        mov dword ptr [0x58fddc], 1
        pushad
        mov eax, dword ptr [0x58fd20]
        test eax, eax
        jz nobuf
        call 0x51d834
        mov dword ptr [0x58fd20], 0
    nobuf:
        call 0x475410
        popad
        ret
    ''')
    # 0x450038: mov [0x58fde4], edx (6 bytes)
    p.patch(0x450038, '8915e4fd5800', call_rel(0x450038, w_reset) + b'\x90')

    # ---- Fix U: tactical AUTO gives orders to the local player's units only -----------------------------
    # The AUTO checkbox in a manual tactical combat ([0x5cb254], local UI state) makes FUN_00474490 call the
    # side-wide combat AI FUN_00477670 (0x474589). That AI orders every unit of the side that has no orders yet,
    # including the ships of an allied AI empire, and marks them "ordered" (+0x20c bit 1, stations +0x330 bit 0).
    # Only the local unit's order is sent (message 0x6e); the other computers let the real AI order the allied
    # ships, with combat RNG draws -> battle checksum assert (battle.c line 909, eventListCRC) -> "Disconnected".
    # Found by a static code review (fits an unexplained player report of battle.c:909 late in a game).
    # Around that call all active units of other owners are marked "ordered" temporarily; exactly the marks set
    # here are removed afterwards (bitmap on the stack, up to 16384 units: the array also holds projectile slots,
    # so 2048 could be exceeded in a large battle; review finding S3).
    # The AI's second pass (review finding R7, static) re-plans every ship of the side whose order is 10, without
    # checking the "ordered" mark or the owner (0x477e98 -> FUN_00478370 at 0x477eb8): an allied player's ship with
    # order 10 would be re-planned on this machine only. While AUTO runs (flag d_auto), that pass now skips ships
    # of other owners.
    d_auto = DATA2 + 0x00
    autoown = put('autoown', f'''
        push ebp
        mov ebp, esp
        sub esp, 0x800
        push eax
        push ecx
        push edx
        push ebx
        push esi
        push edi
        lea edi, [ebp-0x800]
        xor eax, eax
        mov ecx, 0x200
        rep stosd
        mov esi, dword ptr [0x597864]
        xor edx, edx
    mark:
        cmp edx, dword ptr [0x602b14]
        jge marked
        cmp edx, 0x4000
        jge marked
        test byte ptr [esi+0x1b0], 1
        jz mnext
        movzx eax, word ptr [esi+0x1dc]
        movzx ecx, byte ptr [0x5a2b2a]
        cmp eax, ecx
        je mnext
        mov eax, dword ptr [esi+0x178]
        cmp eax, 1
        jne mstation
        test byte ptr [esi+0x20c], 2
        jnz mnext
        or byte ptr [esi+0x20c], 2
        bts dword ptr [ebp-0x800], edx
        jmp mnext
    mstation:
        cmp eax, 5
        jne mnext
        test byte ptr [esi+0x330], 1
        jnz mnext
        or byte ptr [esi+0x330], 1
        bts dword ptr [ebp-0x800], edx
    mnext:
        add esi, 0x3c8
        inc edx
        jmp mark
    marked:
        pop edi
        pop esi
        pop ebx
        pop edx
        pop ecx
        pop eax
        mov dword ptr [{d_auto:#x}], 1
        call 0x477670
        mov dword ptr [{d_auto:#x}], 0
        pushad
        mov esi, dword ptr [0x597864]
        xor edx, edx
    clear:
        cmp edx, dword ptr [0x602b14]
        jge cleared
        cmp edx, 0x4000
        jge cleared
        bt dword ptr [ebp-0x800], edx
        jnc cnext
        cmp dword ptr [esi+0x178], 1
        jne cstation
        and byte ptr [esi+0x20c], 0xfd
        jmp cnext
    cstation:
        and byte ptr [esi+0x330], 0xfe
    cnext:
        add esi, 0x3c8
        inc edx
        jmp clear
    cleared:
        popad
        mov esp, ebp
        pop ebp
        ret
    ''')
    p.patch(0x474589, call_rel(0x474589, 0x477670), call_rel(0x474589, autoown))
    autopass2 = put('autopass2', f'''
        cmp dword ptr [eax+0x1fc], 0xa
        jne 0x477c2c
        cmp dword ptr [{d_auto:#x}], 0
        je go
        push ecx
        push edx
        movzx ecx, word ptr [eax+0x1dc]
        movzx edx, byte ptr [0x5a2b2a]
        cmp ecx, edx
        pop edx
        pop ecx
        jne 0x477c2c
    go:
        jmp 0x477eb4
    ''')
    # 0x477ea7: cmp dword ptr [eax+0x1fc],10 / jne 0x477c2c (13 bytes); EAX = unit, ECX = side entry
    p.patch(0x477ea7, '83b8fc0100000a0f8578fdffff', jmp_rel(0x477ea7, autopass2) + b'\x90' * 8)

    # ---- Fix L: options message 0x85 is parked while a turn is processed -----------------------------------
    # The host sends 0x85 whenever it closes the options dialog while idle. A client that is still processing
    # the turn and pumps messages (e.g. in a dialog) handled it at once: FUN_0050d390 asserts busy != 1
    # (conninit.c line 617) -> Crash.log, "Disconnected"; without the assert the client would switch combat
    # mode / random events in the middle of the turn. The Fix B dispatcher (above) now parks 0x85 like
    # 0x68/0x74 and replays it in arrival order when processing ends. Found by static code reviews (audit R6).
    # The same holds for the save-game messages 0x72/0x73 (host loads a multiplayer save): a client still
    # processing a turn replaced the whole game state under its running turn pipeline (FUN_0050dd30 /
    # FUN_0050f830 -> FUN_004387f0); they are parked too and applied once the turn has finished.

    # ---- Fix K: the turn timer does not end the turn from inside a dialog ---------------------------------
    # With a turn time limit, the timer callback (0x4b9e50) runs from every message pump, also the one of a
    # modal dialog such as "delete current build?" (FUN_00500350 from FUN_004fd7b8). On expiry it sends this
    # player's orders (FUN_00458120 at 0x4b9f74); when the player then confirms the dialog, the handler kills
    # and adds orders that were never sent -> sync error. The expiry is now deferred while a DispatchMessage
    # is in progress (nesting depth counter of Fix E) and taken on a later tick in the main loop.
    tlim = put('timerguard', f'''
        cmp dword ptr [{d_depth:#x}], 0
        jne later
        mov dword ptr [0x59305c], 1
        jmp 0x4b9f74
    later:
        jmp 0x4b9ec0
    ''')
    # 0x4b9f6a: mov dword ptr [0x59305c], 1 (10 bytes)
    p.patch(0x4b9f6a, 'c7055c30590001000000', jmp_rel(0x4b9f6a, tlim) + bytes(5 * [0x90]))

    # ---- Fix V: a remote delete request only matches an order of the requesting empire ------------------
    # Delete requests (type 9, FUN_00457940) carry only the target's sequence number; the matcher of mode 2
    # (0x457b50) compared nothing else. Sequence numbers are per-computer counters, so a receiver that does
    # not have the target (e.g. a build started this turn, bug M) could delete an unrelated order with the same
    # number, and the Fix M fallback would not run. Players only delete orders of their own empire, and the
    # request is created with the local empire (0x45799e): the matcher now also requires the same empire and
    # never matches another delete request. Found by a static code review.
    match9 = put('match9', f'''
        mov ebx, dword ptr [eax]
        cmp ebx, dword ptr [ecx]
        jne no
        cmp dword ptr [eax+0x10], 9
        je no
        mov ebx, dword ptr [edx]
        mov bx, word ptr [ebx+8]
        cmp bx, word ptr [eax+8]
        jne no
        jmp 0x457b62
    no:
        jmp 0x457b5d
    ''')
    # 0x457b57: mov ebx,[eax] / cmp ebx,[ecx] / je 0x457b62 (6 bytes)
    p.patch(0x457b57, '8b183b1974' + p.read(0x457b5c, 1).hex(), jmp_rel(0x457b57, match9) + bytes([0x90]))

    # ---- Fix X: wormhole exit does not depend on the local galaxy-map view ---------------------------------
    # A task force entering a wormhole (mission 13, FUN_00469890) is moved to the partner wormhole's position,
    # converted with the galaxy-map widget's view transform (FUN_004d8200 -> [[0x595554]+0x6c], used by
    # FUN_004dbcd0 / FUN_004dbc00: view origin +0xc/+0x10, zoom +0x1c). That is the local player's scroll and
    # zoom state, so the exit sector differed between computers -> sync error (task forces, military sectors).
    # The transform now gets a fixed view (origin 0/0, zoom 1), which puts the task force at the partner
    # wormhole on every computer. Found by a static code review.
    view = code
    p.write(view, bytes(0x1c) + struct.pack('<I', 1))
    code += 0x20
    # 0x469952: call FUN_004d8200 (5 bytes) -> mov eax, view
    p.patch(0x469952, call_rel(0x469952, 0x4d8200), bytes([0xb8]) + struct.pack('<I', view))

    # ---- Fix Y: a player who leaves after ending the turn no longer blocks the turn barrier ---------------
    # Received orders wait in one of four slots ([0x5b4870 + slot*8]: list, +4 empire). When a player drops,
    # FUN_00457dc0 empties his slot but leaves the list pointer set; the barrier mask is built from all slots
    # with a pointer (FUN_004561b0) and compared with the human mask (0x4581ab), so after a player had already
    # ended the turn and then dropped, every machine that had his orders waited for ever. The slot is now
    # released like at the end of a merge (FUN_00455ec0: destroy list, pointer 0, empire 0xff). Found by a
    # static code review.
    slotfree = put('slotfree', f'''
        mov eax, dword ptr [ecx+0x5b4870]
        call 0x51b520
        mov eax, dword ptr [ecx+0x5b4870]
        xor edx, edx
        call 0x51b450
        mov dword ptr [ecx+0x5b4870], 0
        mov byte ptr [ecx+0x5b4874], 0xff
        jmp 0x457df9
    ''')
    # 0x457dee: mov eax,[ecx+0x5b4870] / call 0x51b520 (11 bytes)
    p.patch(0x457dee, '8b8170485b00' + call_rel(0x457df4, 0x51b520).hex(), jmp_rel(0x457dee, slotfree) + bytes(6 * [0x90]))

    # Safety net for the same barrier: the mask of players whose orders are in (FUN_004561b0) is ANDed with the
    # human mask [0x5a2b28], so a slot of a player who dropped or was eliminated (an eliminated player could
    # still press END TURN and claim a slot, FUN_004565a0 does not check the sender) never blocks the others.
    barmask = put('barmask', f'''
        mov al, dl
        and al, byte ptr [0x5a2b28]
        pop edx
        pop ecx
        ret
    ''')
    # 0x4561dd: mov al,dl / pop edx / pop ecx / ret (5 bytes)
    p.patch(0x4561dd, '88d05a59c3', jmp_rel(0x4561dd, barmask))

    # ---- Fix Z: the sync checksums cover what they are meant to cover (detection only) ---------------------
    # Military sectors (FUN_00466360): the N sector records are copied as 8 bytes each into a buffer, but the
    # CRC got the record count N as byte length, so 7/8 of the buffer was never compared and a sector
    # divergence went unnoticed until it hit another checksum. After the copy loop EBX points behind the last
    # record, so the length is now EBX - buffer (N = 0: loop skipped, EBX = buffer, length 0 as before).
    # 0x4663cc: mov edx,[esp+4] / mov eax,[esp] (7 bytes) -> mov eax,[esp] / mov edx,ebx / sub edx,eax
    p.patch(0x4663cc, '8b5424048b0424', '8b042489da29c2')
    # Diplomacy (FUN_0045d570) sorts its records by id +0x2c before the CRC so that the hash-table order does
    # not matter, but the compare function 0x45d670 compared the first record with itself: it never returned
    # -1, so the sort did not produce one canonical order. Now first.id < second.id -> -1, == -> 0, > -> 1.
    # 0x45d677: mov ebx,[ecx+0x2c] -> mov ebx,[edx+0x2c]; 0x45d67e: cmp ebx,[edx+0x2c] -> cmp eax,ebx / nop
    p.patch(0x45d677, '8b592c', '8b5a2c')
    p.patch(0x45d67e, '3b5a2c', '39d890')
    # Both were found by a static code review (Codex gpt-6-astra).

    # ---- Fix O: stations of an eliminated empire are all removed ---------------------------------------
    # When an empire loses its last colony, FUN_0043af70 walks the station array [0x5a36d0] (count word
    # [0x5a36c0], record 0x5c) and deletes the empire's stations with FUN_0044b000, which moves the following
    # records down by one. The loop then advanced its index anyway (0x43afec jmp 0x43afa3), so the station
    # that moved into the freed slot was skipped and stayed on the map with the owner of a dead empire.
    # The same happens on every computer (no desync), but the orphan keeps taking part in the map-influence
    # step. After a delete the loop now re-checks the same index (jmp 0x43af80: reload count, same slot).
    # Found by a static code review (Codex gpt-6-astra).
    p.patch(0x43afec, 'ebb5', 'eb92')

    # ---- Fix P: changing conquest/liberation of a running invasion mission is no longer lost ------------
    # At End Turn FUN_00466700 compares each UI fleet with the real one to decide whether a new fleet order
    # must be sent. The mission parameter +0x30 was only compared for mission 1; for the invasion mission
    # 0x0e the dialog writes conquer (1) / liberate (2) into +0x30, but with an unchanged path the fleets
    # counted as equal and no order was sent: the old choice was executed on every computer (no desync, but
    # the player's command was lost). For mission 0x0e a changed +0x30 now takes the same branch as a changed
    # path (0x4667b1: FUN_00466468 replaces the order, result "not equal"). Found by a static code review
    # (Codex gpt-6-astra).
    invparm = put('invparm', '''
        cmp dword ptr [eax+0x2c], 1
        je 0x466722
        cmp dword ptr [eax+0x2c], 0xe
        jne 0x4667a9
        mov edx, dword ptr [eax+0x30]
        cmp edx, dword ptr [ebx+0x30]
        jne 0x4667b1
        jmp 0x4667a9
    ''')
    # 0x466718: cmp dword ptr [eax+0x2c],1 / jne 0x4667a9 (10 bytes)
    p.patch(0x466718, '83782c01' + '0f85' + struct.pack('<i', 0x4667a9 - 0x466722).hex(),
            jmp_rel(0x466718, invparm) + b'\x90' * 5)

    # ---- Fix Q: colonize order of a task force that lost its colony ship no longer crashes ---------------
    # Combat runs before the phase-1 missions of the turn. If it destroys the last colony ship of a task force
    # with a colonize order but other ships survive, the task force's colony-ship id +0x44 becomes -1, the
    # order stays, and the colonize executor FUN_004699d0 looks up ship -1 (0x469a5c -> null) and reads
    # ship+0x52 at 0x469ad4: access violation, Crash.log, everybody else sees "Disconnected". Now a missing
    # ship takes the existing "cannot colonize" exit 0x469d60 (order removed locally with mode 0 on every
    # computer, mission reset) before anything is changed. Found by a static code review (Codex gpt-6-astra).
    colship = put('colship', '''
        mov dword ptr [esp+0x1cc], eax
        test eax, eax
        jne 0x469a68
        xor edx, edx
        jmp 0x469d60
    ''')
    # 0x469a61: mov [esp+0x1cc], eax (7 bytes)
    p.patch(0x469a61, '898424cc010000', jmp_rel(0x469a61, colship) + b'\x90' * 2)

    # ---- Fix G: the system screen no longer crashes on a system that is not the player's -----------------
    # The system screen (handler around 0x4f7647) shows the system stored in its widget ([[0x595da8]+0x1c]) and
    # builds the list of sister systems by walking the system list of that system's owner (empire record
    # 0x5b1a98 + owner*0x1bc, list +0x50, callback 0x4f7960) at 0x4f7682 and, on refresh, at 0x4f7b4f. The owner
    # is not checked: when the stored system is not one of the player's (seen in a 5-player test game: player B,
    # turn 179, after F2) and its owner is a minor race, rebels or nobody (owner >= 5), the "list" is read from
    # the wrong memory: access violation at 0x51b429, and everybody else sees "Disconnected". Reproduced by making
    # the stored system an unowned one at 0x4f7647: the original crashes exactly like B. Now the screen first
    # replaces a stored system that is not the player's by the player's first system; if he has none, the two
    # list walks are skipped for owner >= 5 (empty list).
    sysfix = put('sysfix', '''
        mov esi, dword ptr [0x595da8]
        push eax
        push ecx
        push edx
        push ebx
        movsx eax, word ptr [esi+0x1c]
        movzx ecx, word ptr [0x5a36bc]
        cmp eax, 0
        jl search
        cmp eax, ecx
        jge search
        imul edx, eax, 0x328
        add edx, dword ptr [0x5a36c8]
        mov bl, byte ptr [edx+0x4c]
        cmp bl, byte ptr [0x5a2b2a]
        je ok
    search:
        xor eax, eax
        mov edx, dword ptr [0x5a36c8]
        mov bl, byte ptr [0x5a2b2a]
    next:
        cmp eax, ecx
        jge ok
        cmp byte ptr [edx+0x4c], bl
        je found
        add edx, 0x328
        inc eax
        jmp next
    found:
        mov word ptr [esi+0x1c], ax
    ok:
        pop ebx
        pop edx
        pop ecx
        pop eax
        jmp 0x4f764d
    ''')
    # 0x4f7647: mov esi,[0x595da8] (6 bytes)
    p.patch(0x4f7647, '8b35a85d5900', jmp_rel(0x4f7647, sysfix) + b'\x90')
    sysa = put('sysa', '''
        mov cl, byte ptr [edx+0x4c]
        cmp cl, 5
        jae 0x4f76b5
        lea eax, [ecx*8]
        jmp 0x4f768c
    ''')
    # 0x4f7682: mov cl,[edx+0x4c] / lea eax,[ecx*8+0] (10 bytes)
    p.patch(0x4f7682, '8a4a4c8d04cd00000000', jmp_rel(0x4f7682, sysa) + b'\x90' * 5)
    sysb = put('sysb', '''
        xor edx, edx
        mov dl, byte ptr [ebx+0x4c]
        cmp dl, 5
        jae 0x4f7b82
        jmp 0x4f7b52
    ''')
    # 0x4f7b4d: xor edx,edx / mov dl,[ebx+0x4c] (5 bytes)
    p.patch(0x4f7b4d, '31d28a534c', jmp_rel(0x4f7b4d, sysb))

    # ---- Fix F: combat units start zeroed, so monsters decide the same way on every computer -----------------
    # The combat unit array [0x597864] ([0x602b14] units of 0x3c8 bytes) is allocated at 0x520e2e with
    # FUN_00492f10, which does not clear the memory. Ships set +0x364 to 0 (0x521616), monsters (type 7) never do,
    # but the monster combat AI FUN_0047715c tests +0x364 bit 0 for race 0x26 (0x4771bd) and for the Edo Guardian
    # (0x477481): set means passive this round. The byte is whatever an earlier allocation left in that heap
    # block, which differs between computers, so a monster could attack on one machine and hold back on another:
    # different combat random numbers, battle checksum failure, "Disconnected". Found by a static code review
    # (Codex gpt-6-astra). The array is now cleared after the allocation (like calloc); every other field is
    # still set by the unit initialisation as before.
    unitzero = put('unitzero', '''
        push ecx
        push eax
        call 0x492f10
        pop ecx
        test eax, eax
        je done
        push edi
        push eax
        mov edi, eax
        xor eax, eax
        cld
        rep stosb
        pop eax
        pop edi
    done:
        pop ecx
        ret
    ''')
    # 0x520e2e: call FUN_00492f10 (eax = size)
    p.patch(0x520e2e, call_rel(0x520e2e, 0x492f10), call_rel(0x520e2e, unitzero))
    # The tactical task-force array [0x597860] (count x 0x74, allocated right after) has the same problem: its
    # initialisation writes +0x00..+0x20 and +0x3c..+0x54 only, but the retreat behaviour of order 10
    # (FUN_0056c1f8, ai\retreat.c, 0x56c2cb..0x56c358) reads the three doubles at +0x24..+0x3b as an aim point, so
    # a retreating unit steered by heap leftovers that differ between computers (battle checksum assert). Found by
    # a static code review (Claude Sonnet). The array is cleared the same way.
    # 0x520ef3: call FUN_00492f10 (eax = count * 0x74)
    p.patch(0x520ef3, call_rel(0x520ef3, 0x492f10), call_rel(0x520ef3, unitzero))

    # ---- Fix CA: conquering the last system of an empire when it is its original capital ------------------
    # After an invasion (FUN_00466cf0) the loser's home-system entry [0x5b2360 + emp*2] is set to the first
    # system of its system list (0x467e9b: list [emp record + 0x50], FUN_0051bb00 = first entry or 0). When the
    # conquered capital was the empire's last system the list is already empty and 0x467ea9 reads the word at
    # address 0: access violation on every computer, the game ends for everybody. Found by a static code review
    # (Claude Fable). An empty list now stores 0x3e80, the game's own "no home system" value (0x467f4d).
    capnone = put('capnone', '''
        mov dx, word ptr [ecx+0x44]
        test eax, eax
        je none
        mov ax, word ptr [eax]
        jmp 0x467eac
    none:
        mov ax, 0x3e80
        jmp 0x467eac
    ''')
    # 0x467ea5: mov dx,[ecx+0x44] / mov ax,[eax] (7 bytes)
    p.patch(0x467ea5, '668b5144668b00', jmp_rel(0x467ea5, capnone) + b'\x90' * 2)

    # ---- Fix EL: orders of an eliminated (or dropped) player are no longer merged ---------------------------
    # An eliminated human keeps his game open; his machine never calculates a turn again, but END TURN (or the turn
    # timer) still sends his whole order list (message 0x68, FUN_00458120 -> FUN_00456340). The receivers file it
    # in a receive slot and the merge FUN_00455ec0 takes every slot with a list, whatever the sender. Because that
    # message is not part of the turn barrier any more (Fix Y), it arrives before the turn on one machine and after
    # it on another: the same diplomacy/intel orders are applied in different turns -> sync error. Found by a
    # static code review (Claude Fable). The merge now takes a slot only if its player is still in the human mask
    # [0x5a2b28]; other slots are released like at the end of a merge (list destroyed, pointer 0, empire 0xff).
    # A player eliminated during a turn is still in the mask when that turn's orders are merged.
    elmerge = put('elmerge', '''
        mov ebx, dword ptr [ecx+0x5b4870]
        test ebx, ebx
        je next
        push eax
        push edx
        movzx edx, byte ptr [ecx+0x5b4874]
        cmp edx, 8
        jae keep
        mov eax, 1
        push ecx
        mov cl, dl
        shl eax, cl
        pop ecx
        test al, byte ptr [0x5a2b28]
        jne keep
        mov eax, dword ptr [ecx+0x5b4870]
        call 0x51b520
        mov eax, dword ptr [ecx+0x5b4870]
        xor edx, edx
        call 0x51b450
        mov dword ptr [ecx+0x5b4870], 0
        mov byte ptr [ecx+0x5b4874], 0xff
        pop edx
        pop eax
    next:
        jmp 0x455f05
    keep:
        pop edx
        pop eax
        jmp 0x455ffb
    ''')
    # 0x455ef7: mov ebx,[ecx+0x5b4870] / test ebx,ebx / jne 0x455ffb (14 bytes)
    p.patch(0x455ef7, '8b9970485b0085db0f85f6000000', jmp_rel(0x455ef7, elmerge) + b'\x90' * 9)

    # ---- Fix OP: closing the options dialog no longer changes the game's rules on one machine only ----------
    # FUN_004cdb80 (ACCEPT or Escape in the options dialog) copies the dialog's tactical-combat mode and random-
    # events switch into the running game ([0x5a2b68] at 0x4cdbdc, [0x5a2b46] at 0x4cdbf1), but only the host
    # in the idle state broadcasts them afterwards (0x4cdc4f..0x4cdc6e: message 0x85). The dialog is filled from
    # the local preferences, not from the game: a client that opens and closes the options (or a host that does
    # it while waiting for the others) silently switches random events or manual combat on his machine only ->
    # different random numbers -> sync error. Found by a static code review (Codex gpt-6-astra). In multiplayer
    # the two game values are now written only when the broadcast follows (host, session flag, idle); the local
    # preferences are still saved as before.
    def opt_guard(name, store, back):
        return put(name, f'''
        cmp dword ptr [0x5a2924], 0
        je write
        cmp dword ptr [0x5a2920], 0
        je skip
        cmp dword ptr [0x5a2990], 0
        je skip
        cmp dword ptr [0x5a291c], 0
        jne skip
    write:
        {store}
    skip:
        jmp {back:#x}
    ''')
    opt_tac = opt_guard('opt_tac', 'mov dword ptr [0x5a2b68], eax', 0x4cdbe1)
    opt_rev = opt_guard('opt_rev', 'mov byte ptr [0x5a2b46], al', 0x4cdbf6)
    # 0x4cdbdc: mov [0x5a2b68],eax (5 bytes); 0x4cdbf1: mov [0x5a2b46],al (5 bytes)
    p.patch(0x4cdbdc, 'a3682b5a00', jmp_rel(0x4cdbdc, opt_tac))
    p.patch(0x4cdbf1, 'a2462b5a00', jmp_rel(0x4cdbf1, opt_rev))

    # ---- Fix IN: intel allocations are not committed while the turn is out of the player's hands -----------
    # Leaving the intel screen commits the sliders (0x4bcb90): an intel order of type 4 is created or an existing
    # pending one is changed in place (0x4bc3e0 -> FUN_00457644), and the player's intel record is written at once
    # (0x47f190). After END TURN the order list has already been sent, so an in-place change and the direct write
    # stay on the player's machine only. The function keys are blocked while waiting, but the screens can still be
    # reached with the mouse. Found by a static code review (Claude Fable). In multiplayer the commit is now
    # skipped while the turn state [0x5a291c] is not idle (the change is dropped on every machine alike). The
    # screen's panel is still hidden as before (0x4bcb93..0x4bcbab; review finding N13).
    intelcommit = put('intelcommit', '''
        cmp dword ptr [0x5a2924], 0
        je go
        cmp dword ptr [0x5a291c], 0
        jne skip
    go:
        push ecx
        push edx
        push ebx
        mov eax, dword ptr [0x5932b4]
        jmp 0x4bcb98
    skip:
        push ecx
        push edx
        push ebx
        mov eax, dword ptr [0x5932b4]
        mov eax, dword ptr [eax]
        call 0x53dbb0
        mov edx, dword ptr [0x5932b4]
        mov edx, dword ptr [edx]
        call 0x53cf30
        pop ebx
        pop edx
        pop ecx
        ret
    ''')
    # 0x4bcb90: push ecx / push edx / push ebx / mov eax,[0x5932b4] (8 bytes)
    p.patch(0x4bcb90, '515253a1b4325900', jmp_rel(0x4bcb90, intelcommit) + b'\x90' * 3)

    # ---- Fix F6: the F6 key no longer spawns a monster on one machine only ------------------------------------
    # F6 is a leftover debug key: the keyboard handler FUN_00401910 sets bit 2 of [0x5a2b6c] (0x401ad7) whenever a
    # game is running; unlike the F9-F11 cheats it checks neither the cheat flag nor multiplayer. With random events
    # on, the next turn's event step FUN_0044cbe0 (0x44cbe4) then spawns a random monster (FUN_0044b220, several
    # main random numbers) and resets the spawn countdown [0x58fdb0] - on the machine whose player pressed F6 only:
    # one key press -> "synchronization error" at the next turn (reproduced: seed and checksums differ, countdown
    # 40 vs 54). Found by static code reviews (Claude Sonnet and Fable). In multiplayer the key is now ignored.
    f6 = put('f6', '''
        cmp dword ptr [0x5a2924], 0
        jne skip
        or byte ptr [0x5a2b6c], 4
    skip:
        jmp 0x401976
    ''')
    # 0x401ad7: or byte ptr [0x5a2b6c],4 (7 bytes), followed by jmp 0x401976
    p.patch(0x401ad7, '800d6c2b5a0004', jmp_rel(0x401ad7, f6) + b'\x90' * 2)

    # ---- Fix HA: shipyard loss kills the system's ship order on every machine (Fix H, arm A) -------------------
    # When a system loses its shipyard during turn processing (scrap order, bombardment, unrest), FUN_00445a10
    # decides at 0x445a28 from the current-production record (+0x80 == 3: building a ship) whether to kill the
    # system's production order. For a human player's system that record is kept in owner form: after the turn
    # processing advanced the queue to a ship (owner only, FUN_0046138c) or after a ship was picked in the build
    # screen, the owner has 3 and every other machine 0 until the order runs. In that turn only the owner kills the
    # ship order; the others keep it and put the system's industry into the ship although the shipyard is gone ->
    # "synchronization error" at the end of the same turn. Reproduced with trek_t_fix18 from saves/five_1201_t103
    # (tools/n7test.sh: buy the Heavy Cruiser at Cardassia with a second one queued, scrap the Union Shipyard in the
    # next turn): heartbeat mismatch at turn 105, B..E invest 3163 into the ship, A builds the next structure.
    # Found by static code reviews (Claude Sonnet, review finding N7). In multiplayer every machine now kills the
    # ship orders of a human player's system there, decided from the order list (equal everywhere) instead of the
    # record: the kill pattern becomes "ship, any class" (FUN_00463820 with class -1) instead of "any production
    # order", so a structure being built is not touched. Computer empires' systems and single player keep the
    # original test. The record test at 0x445a78 (clear the record, owner restarts the queue: Fix H) is unchanged.
    hahuman = put('hahuman', '''
        cmp dword ptr [0x5a2924], 0
        je no
        push eax
        movzx eax, byte ptr [esi+0x4c]
        cmp eax, 5
        jae no_pop
        bt dword ptr [0x5a2b28], eax
        pop eax
        ret
    no_pop:
        pop eax
    no:
        clc
        ret
    ''')
    hagate = put('hagate', f'''
        call {hahuman:#x}
        jc 0x445a3d
        cmp dword ptr [esi+0x80], 3
        je 0x445a3d
        jmp 0x445a31
    ''')
    hapattern = put('hapattern', f'''
        call {hahuman:#x}
        jnc 0x4638d0
        push ebx
        or ebx, -1
        call 0x463820
        pop ebx
        ret
    ''')
    # 0x445a28: cmp dword ptr [esi+0x80],3 / je 0x445a3d (9 bytes)
    p.patch(0x445a28, '83be8000000003740c', jmp_rel(0x445a28, hagate) + b'\x90' * 4)
    # 0x445a4d: call FUN_004638d0 (eax = order pattern, edx = system)
    p.patch(0x445a4d, call_rel(0x445a4d, 0x4638d0), call_rel(0x445a4d, hapattern))

    # ---- Fix IE: an elimination no longer deletes the pending intel orders -------------------------------------
    # When an empire is eliminated during turn processing (0x43b370 -> FUN_0047f6d0), the game moves every other
    # empire's intel allocations away from the dead empire, both in the intel records and, in FUN_0047fa90, in the
    # pending intel orders of type 4 (changed in place through FUN_00457644). It then deletes every intel order of
    # every empire (0x47fba5, kill mode 0), also priorities and blame orders. But a player who left the intel
    # screen this turn already wrote the new allocations into his own record (0x4bcb90 -> FUN_0047f190); the other
    # machines would only apply them from that order in the intel phase FUN_0047f7d0, later in the same turn. So the
    # player's allocations stay different on his machine (reproduced with tools/r2intel.py from
    # saves/five_1201_t103: A commits 60/0/40, the cleanup runs in the research step on every machine -> A keeps
    # 60/0/40, B..E keep 50/50); his intel then works differently on each machine. Found by static code reviews
    # (review finding R2: Codex Astra and Sol, Claude Sonnet and Fable). In multiplayer the orders are now kept: the
    # intel phase applies them, with the dead empire's share already moved, on every machine alike.
    intelkeep = put('intelkeep', '''
        cmp dword ptr [0x5a2924], 0
        jne keep
        jmp 0x4576c4
    keep:
        ret
    ''')
    # 0x47fba5: call FUN_004576c4 (eax = selected copy of the order, edx = 0)
    p.patch(0x47fba5, call_rel(0x47fba5, 0x4576c4), call_rel(0x47fba5, intelkeep))
    # 0x47fb6e: mov ebx,1 -> mov ebx,esi: the loop over espionage (1) and sabotage (2) passed category 1 twice, so
    # a pending order kept its sabotage share against the dead empire (the records lose it)
    p.patch(0x47fb6e, 'bb01000000', '89f3909090')

    # ---- Fix MS: the empire morale average sums in 32 bits -----------------------------------------------------
    # FUN_00461100 adds the morale (+0x44, about 0..200) of every system of an empire in the 16-bit register DI
    # (0x46118c) and divides the sign-extended sum (0x4611c2). From about 164 systems at high morale the sum wraps
    # negative, the average fails the range assert in FUN_00465b60 (morale.c line 102) and the game ends on every
    # machine. Found by static code reviews (review finding S2). The sum is now 32 bits wide.
    morsum = put('morsum', '''
        mov edx, dword ptr [esp]
        lea eax, [ebx+0x240]
        add eax, edx
        movsx edx, word ptr [eax+0x44]
        add edi, edx
        jmp 0x461190
    ''')
    # 0x461181: mov edx,[esp] / lea eax,[ebx+0x240] / add eax,edx / add di,[eax+0x44] (15 bytes)
    p.patch(0x461181, '8b14248d834002000001d066037844', jmp_rel(0x461181, morsum) + b'\x90' * 10)
    # 0x4611c2: movsx edx,di -> mov edx,edi
    p.patch(0x4611c2, '0fbfd7', '89fa90')

    # ---- Fix MI: invading a system whose native minor race is extinct no longer crashes ------------------------
    # When a system is liberated or conquered, FUN_00466cf0 marks the native minor race's record (+0x3c). For a race
    # whose bit is set in [0x5a2b50] (eliminated) the inlined record lookup yields a null pointer, and the write to
    # address 0x3c (0x4679a1 liberate, 0x467fe0 conquer) ends the game on every machine. Reached when a minor
    # race's home system was bombarded to extinction and a fleet with the invasion mission then takes it. Found by
    # a static code review (Claude Fable, review finding N11). The write is now skipped for an eliminated race.
    p.patch(0x46799f, '31c0', 'eb07')        # jmp 0x4679a8 (after the write)
    p.patch(0x467fde, '31c0', 'eb07')        # jmp 0x467fe7

    # ---- Fix RS: research allocations are not committed while the turn is out of the player's hands -----------
    # Leaving the research screen (close handler 0x4d2910) commits the allocation sliders: FUN_004d2780 changes a
    # pending research order in place or adds one, and writes the empire's research record at once (0x4d281b). With
    # a turn timer the turn can end while the screen is open; the order list is already sent then, so the change
    # stays on the player's machine (reproduced with tools/r1timer.py in a game with a one-minute timer: B leaves
    # the screen after the timer ended its turn -> B researches with 40/12/12/12/12/12, the others with the old
    # 17/17/17/17/16/16). Found by static code reviews (review finding R1). Same rule as Fix IN: in multiplayer the
    # commit is skipped while the turn state [0x5a291c] is not idle (the change is dropped on every machine alike).
    rescommit = put('rescommit', '''
        cmp dword ptr [0x5a2924], 0
        je go
        cmp dword ptr [0x5a291c], 0
        jne skip
    go:
        jmp 0x4d2780
    skip:
        ret
    ''')
    # 0x4d292a: call FUN_004d2780 (after the panel was hidden)
    p.patch(0x4d292a, call_rel(0x4d292a, 0x4d2780), call_rel(0x4d292a, rescommit))

    # ---- Fix RD: no task-force reorganisation after the turn ended ----------------------------------------------
    # The REDEPLOY dialog (0x4ffde0) changes the real task forces at once: FUN_004feea0 (new task force for a ship),
    # FUN_004fef90 (ship leaves its task force) and FUN_004ff0a0 (ship joins one) write the ship's task-force id
    # (+0x50, part of the ship checksum) and create or remove task forces. END TURN turns the changes made so far into
    # orders (FUN_004667d0 at 0x45812c); a change made after that exists on this machine only. The dialog is a child
    # window that the END TURN lock does not disable, so with a turn timer it can stay usable after the timer ended
    # the turn. Found by static code reviews (review finding S4, static; the dialog's three callbacks are only called
    # from its handlers 0x4fe020 and 0x4fe500). In multiplayer they now do nothing while the turn is not idle.
    def turn_guard(name, entry, head, cont):
        cave = put(name, f'''
            cmp dword ptr [0x5a2924], 0
            je go
            cmp dword ptr [0x5a291c], 0
            jne skip
        go:
            {head}
            jmp {cont:#x}
        skip:
            ret
        ''')
        n = cont - entry
        p.patch(entry, p.read(entry, n).hex(), jmp_rel(entry, cave) + b'\x90' * (n - 5))
    turn_guard('rdnew', 0x4feea0, 'push ebx\n push ecx\n push esi\n push edi\n push ebp', 0x4feea5)
    turn_guard('rdleave', 0x4fef90, 'push ebx\n push ecx\n push edx\n push esi\n push edi', 0x4fef95)
    turn_guard('rdjoin', 0x4ff0a0, 'push ecx\n push edi\n mov edi, edx\n movsx ecx, dx', 0x4ff0a7)

    out["code_end"] = code
    return out
