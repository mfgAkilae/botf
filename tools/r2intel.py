"""Review finding R2: an elimination deletes every pending intel order. Run while all games are idle, before TURN.
  r2intel.py commit <inst> <v0..v8>   leave the intel screen of <inst> with these slider values (security,
                                      espionage x4, sabotage x4 in %): the game makes an intel order and writes the
                                      player's own record at once
  r2intel.py inject <emp>             in the next turn processing, call the elimination cleanup FUN_0047f6d0(emp)
                                      on every game (research step, 0x453824 redirected to a stub in the test shim,
                                      before the intel phase FUN_0047f7d0)
  r2intel.py show <inst>              intel record of <inst>'s empire (0x5a3aec + emp*0x2c1c + 0x70, 9 values) in
                                      every game"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from asmutil import asm, call_rel

STUB, PAR = 0x69e1a0, 0x69e1f0          # free tail of build_test.py's .tstshim section (as tools/r4inject.py)
u32 = lambda pid, a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
st = H.load_state(); P = {k: st[k] for k in 'ABCDE' if k in st and H.pid_alive(st[k])}
cmd = sys.argv[1]


def key(pid, vk):
    hw = H.main_window(pid); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)


if cmd == 'commit':
    pid = P[sys.argv[2]]; vals = [int(v) for v in sys.argv[3:12]]
    key(pid, 0x70); time.sleep(0.5); key(pid, 0x72); time.sleep(1.2)
    ui = u32(pid, 0x5cb4b4)
    print('screen before', [struct.unpack('<i', H.readmem(pid, ui + 0x1c + 4 * i, 4))[0] for i in range(9)])
    for i, v in enumerate(vals):
        H.writemem(pid, ui + 0x1c + 4 * i, struct.pack('<i', v))
    key(pid, 0x70); time.sleep(0.8)
elif cmd == 'inject':
    emp = int(sys.argv[2])
    code = asm(f'''
        call 0x452ee0
        cmp dword ptr [{PAR:#x}], 0
        je done
        pushad
        mov eax, dword ptr [{PAR + 4:#x}]
        call 0x47f6d0
        popad
        mov dword ptr [{PAR:#x}], 0
    done:
        ret
    ''', STUB)
    assert STUB + len(code) <= PAR
    for x, pid in P.items():
        H.writemem(pid, STUB, code)
        H.writemem(pid, PAR, struct.pack('<II', 1, emp))
        H.writemem(pid, 0x453824, call_rel(0x453824, STUB))
        print(x, 'armed: elimination cleanup for empire %d' % emp)
elif cmd == 'show':
    emp = H.readmem(P[sys.argv[2]], 0x5a2b2a, 1)[0]
    for x, pid in P.items():
        print(x, [struct.unpack('<i', H.readmem(pid, 0x5a3aec + emp * 0x2c1c + 0x70 + 4 * i, 4))[0] for i in range(9)],
              'armed' if H.readmem(pid, PAR, 4) != bytes(4) else '')
