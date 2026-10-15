"""Fix Q test: the next colonize mission that executes (FUN_004699d0) finds its task force without a colony
ship, as after combat destroyed the last colony ship: at 0x469a3f the stub sets the task force's colony-ship id
+0x44 to -1 on every running test instance (same state everywhere). Original: access violation at 0x469ad4;
fixed: the order is dropped and the game goes on. PAR+0 = armed flag (cleared after the injection), PAR+4 =
number of colonize executions seen.
usage: colinject.py [status]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from asmutil import asm, jmp_rel

STUB, PAR = 0x69e260, 0x69e2e0          # free tail of build_test.py's .tstshim section
st = H.load_state(); P = {k: st[k] for k in 'ABCDE' if k in st and H.pid_alive(st[k])}
if sys.argv[1:] == ['status']:
    for x, pid in P.items():
        print(x, 'armed %d seen %d' % struct.unpack('<II', H.readmem(pid, PAR, 8)))
    raise SystemExit
code = asm(f'''
    mov eax, dword ptr [esp+0x1d4]
    inc dword ptr [{PAR + 4:#x}]
    cmp dword ptr [{PAR:#x}], 0
    je done
    mov word ptr [eax+0x44], 0xffff
    mov dword ptr [{PAR:#x}], 0
done:
    jmp 0x469a46
''', STUB)
assert STUB + len(code) <= PAR
for x, pid in P.items():
    assert H.readmem(pid, 0x469a3f, 7) == bytes.fromhex('8b8424d4010000'), x
    H.writemem(pid, STUB, code)
    H.writemem(pid, PAR, struct.pack('<II', 1, 0))
    H.writemem(pid, 0x469a3f, jmp_rel(0x469a3f, STUB) + b'\x90' * 2)
    print(x, 'armed')
