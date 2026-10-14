"""Build a TEST-ONLY trek.exe: allow multiple instances and drive the cursor from memory.
usage: build_test.py <in.exe> <out.exe> [--fix] [--latency MS] [--delay74 MS]
  --fix          apply the multiplayer fix (netfix.py)
  --latency MS   per-packet sleep in the send loop (emulates a slow link, max 127)
  --delay74 MS   extra delay before the production-queue message 0x74 is sent
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

# 1) single instance check: FindWindow result ignored
p.patch(0x401df9, '89c685c07428', '31c089c67428')

# 1b) keep ticking while the window is inactive (main loop would WaitMessage)
p.patch(0x40232e, '750c', 'eb0c')

# 1c) WM_ACTIVATEAPP always marks the game active. The original only counts the foreground window
#     as active, and the turn-start pump (0x4024c0, called from 0x458170) waits until it is.
#     With two instances on one desktop only one can be foreground, so the other never starts the turn.
p.patch(0x401cca, '85d2', 'eb64')

# 2) cursor shim (first new section -> fixed address 0x69e000)
sec = p.add_section('.tstshim', 0x200, 0xE0000060)
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
    print('netfix', {k: hex(v) for k, v in info.items()})

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

p.save(dst)
json.dump({'cursor_block': blk}, open(dst + '.json', 'w'))
print('ok cursor block %#x' % blk)
