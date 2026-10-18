"""Build a TEST-ONLY trek.exe: allow multiple instances and drive the cursor from memory.
usage: build_test.py <in.exe> <out.exe> [--fix] [--nofixs] [--heapstress N] [--latency MS] [--delay74 MS] [--spike]
  --nofixs       with --fix: leave out Fix S (heap pool serialization), for A/B tests
  --heapstress N with --fix: the network receive thread does N malloc/free pairs every 1 ms
  --fix          apply the multiplayer fix (netfix.py)
  --latency MS   per-packet sleep in the send loop (emulates a slow link, max 127)
  --delay74 MS   extra delay before the production-queue message 0x74 is sent
  --slowend MS   with --fix: stay BUSY (pumping) for MS after the last turn phase, the others are idle meanwhile
  --spike        with --fix: the resync spike (spike_resync.py, docs/resync_design_draft.md section 7) in the
                 enlarged shim section; its data addresses go to <out.exe>.json under 'spike'
  --spike-nopump the spike without the pump override at 0x4024d8 (negative control for inactive windows)
  --spike-snapshot  owner production records from a turn-start snapshot (and the host's turn-start save) instead
                 of the stock restart FUN_0043a0a0 after the load (finding E, variants 3 and 4)
Writes <out.exe>.json with the address of the fake cursor block.
  block+0 fake_x (game coords 0..799), +4 fake_y, +8 enable flag
"""
import json, sys
sys.path.insert(0, __file__.rsplit('\\', 1)[0] if '\\' in __file__ else '.')
from pe import PE
from asmutil import asm, call_rel

src, dst = sys.argv[1], sys.argv[2]
p = PE(src)


def opt(name):
    return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else None


latency = opt('--latency')
delay74 = opt('--delay74')
slowphase = opt('--slowphase')
slowai = opt('--slowai')
slowend = opt('--slowend')

# 1) single instance check: FindWindow result ignored
p.patch(0x401df9, '89c685c07428', '31c089c67428')

# 1b) keep ticking while the window is inactive (main loop would WaitMessage)
p.patch(0x40232e, '750c', 'eb0c')

# 1c) WM_ACTIVATEAPP always marks the game active. The original only counts the foreground window
#     as active, and the turn-start pump (0x4024c0, called from 0x458170) waits until it is.
#     With two instances on one desktop only one can be foreground, so the other never starts the turn.
p.patch(0x401cca, '85d2', 'eb64')

# 2) cursor shim (first new section -> fixed address 0x69e000)
spike = '--spike' in sys.argv or '--spike-nopump' in sys.argv
if spike:
    import spike_resync
    assert '--fix' in sys.argv, '--spike needs --fix (it chains into the Fix B and Fix K caves)'
sec = p.add_section('.tstshim', spike_resync.SECTION_SIZE if spike else 0x200, 0xE0000060)
blk = sec
stub = sec + 0x20
IAT_GETCURSORPOS = 0x574600
code = asm(f'''
    mov eax, [esp+4]
    cmp dword ptr [{blk + 8:#x}], 0
    je real
    mov edx, [{blk:#x}]
    mov [eax], edx
    mov edx, [{blk + 4:#x}]
    mov [eax+4], edx
    mov eax, 1
    ret 4
real:
    jmp dword ptr [{IAT_GETCURSORPOS:#x}]
''', stub)
p.write(stub, code)
for site in (0x515d45, 0x515f8e, 0x516189):
    p.patch(site, '2eff1500465700', call_rel(site, stub) + b'\x90\x90')

if '--fix' in sys.argv:
    import netfix
    info = netfix.apply(p)
    print('netfix', {k: hex(v) if isinstance(v, int) else v for k, v in info.items()})

spike_info = None
if spike:
    spike_info = spike_resync.apply(p, sec, info, pump_override='--spike-nopump' not in sys.argv,
                                    owner_mode='snapshot' if '--spike-snapshot' in sys.argv else 'restart')
    print('spike code', {k: hex(v) for k, v in spike_info['code'].items()})

if latency is not None:
    assert 0 <= latency <= 127
    cur = p.read(0x54e1cd, 2)
    p.patch(0x54e1cd, cur.hex(), bytes([0x6a, latency]))

if delay74 is not None:
    # find the call site of the 0x74 sender (FUN_0044d580) in the end-turn handler
    cave = sec + 0x80
    p.write(cave, asm(f'push {delay74}\ncall dword ptr [0x574594]\njmp 0x44d580', cave))
    for site in (0x458155, 0x45815a):
        if p.read(site, 5) == call_rel(site, 0x44d580):
            p.patch(site, call_rel(site, 0x44d580), call_rel(site, cave))
            print('delay74 at', hex(site))

if slowphase is not None:
    # make turn processing slow right before _turnResolveEconomyPhase2 (label call at 0x45843a)
    cave2 = sec + 0xc0
    p.write(cave2, asm(f'push {slowphase}; call dword ptr [0x574594]; jmp 0x458720', cave2))
    p.patch(0x45843a, call_rel(0x45843a, 0x458720), call_rel(0x45843a, cave2))
    print('slowphase', slowphase)

if slowai is not None:
    # make AIProcessTurn (first turn phase, label call at 0x4582cc) slow -> other machines wait
    cave3 = sec + 0x100
    p.write(cave3, asm(f'push {slowai}; call dword ptr [0x574594]; jmp 0x458720', cave3))
    p.patch(0x4582cc, call_rel(0x4582cc, 0x458720), call_rel(0x4582cc, cave3))
    print('slowai', slowai)

if slowend is not None:
    # Stay in turn processing for <slowend> ms after the last turn phase (right before BUSY is cleared at 0x4586d6)
    # and keep pumping meanwhile: the other machines are idle again while this one is still BUSY (the phases
    # before are synchronous, --slowai delays every machine). Needs --fix (the netfix call at 0x4586d6).
    # chain to whatever the netfix call at 0x4586d6 calls now (Fix B endturn, or Fix LV's lvend in front of it)
    cur = p.read(0x4586d6, 5)
    assert cur[0] == 0xe8
    endturn = (0x4586db + int.from_bytes(cur[1:], 'little', signed=True)) & 0xffffffff
    cave5 = sec + 0x1a0
    p.write(cave5, asm(f'''
        pushad
        mov esi, {max(1, slowend // 100)}
    se_loop:
        push 100
        call dword ptr [0x574594]
        sub esp, 0x20
        mov eax, esp
        call 0x4024c0
        add esp, 0x20
        dec esi
        jne se_loop
        popad
        jmp {endturn:#x}
    ''', cave5))
    assert cave5 + 0x40 <= sec + 0x200
    p.patch(0x4586d6, cur.hex(), call_rel(0x4586d6, cave5))
    print('slowend', slowend)

if '--nofixs' in sys.argv:
    # all fixes except Fix S (default heap pool without MEM_POOL_SERIALIZE), for A/B tests of the heap race
    p.patch(0x5a0a1c, '0280', '0080')
    print('without Fix S')

heapstress = opt('--heapstress')
if heapstress is not None:
    # The network receive thread (Fix D wait loop, 0x517000) wakes every 1 ms instead of 1 s and each time
    # does <heapstress> malloc/free pairs on the default pool, like a burst of incoming game messages
    # (the original allocates one list node per message with malloc on that thread).
    rx = info['rxwait']
    cave4 = sec + 0x140
    p.write(cave4, asm(f'''
        mov ecx, {heapstress}
    hs_loop:
        push ecx
        mov eax, ecx
        and eax, 0xff
        add eax, 8
        call 0x51d760
        test eax, eax
        jz hs_skip
        mov byte ptr [eax], 0x5a
        call 0x51d834
    hs_skip:
        pop ecx
        dec ecx
        jnz hs_loop
        jmp dword ptr [0x5743fc]
    ''', cave4))
    code = p.read(rx, 0x60)
    o = code.index(bytes.fromhex('ff15fc435700'))
    p.patch(rx + o, 'ff15fc435700', call_rel(rx + o, cave4) + b'\x90')
    o = code.index(bytes.fromhex('68e8030000'))
    p.patch(rx + o, '68e8030000', '6a01909090')
    print('heapstress', heapstress)

p.save(dst)
meta = {'cursor_block': blk}
if spike_info:
    meta['spike'] = spike_info['fields']
json.dump(meta, open(dst + '.json', 'w'))
print('ok cursor block %#x' % blk)
