"""Static audit R4 test: run the ship-class refit FUN_0044a360(emp, old, new) once inside the next turn
processing on every running test instance, exactly as a finished research would (the research step
FUN_00453820 calls FUN_00452ee0 first; that call at 0x453824 is redirected to a stub in the test shim section).
Optionally makes one ship of <emp> class <old> first (same ship index on every machine, so the state stays equal).
Run while all games are idle, before TURN.
usage: r4inject.py <emp> <old_class> <new_class> [--make-ship]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from asmutil import asm, call_rel

emp, old, new = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
STUB, PAR = 0x69e1a0, 0x69e1f0          # free tail of build_test.py's .tstshim section
u32 = lambda pid, a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
st = H.load_state(); P = {k: st[k] for k in 'ABCDE' if k in st and H.pid_alive(st[k])}

code = asm(f'''
    call 0x452ee0
    cmp dword ptr [{PAR:#x}], 0
    je done
    pushad
    mov eax, dword ptr [{PAR + 4:#x}]
    mov edx, dword ptr [{PAR + 8:#x}]
    mov ebx, dword ptr [{PAR + 12:#x}]
    call 0x44a360
    popad
    mov dword ptr [{PAR:#x}], 0
done:
    ret
''', STUB)
assert STUB + len(code) <= PAR

idx = None
if '--make-ship' in sys.argv:
    first = P[next(iter(P))]
    obj = u32(first, 0x5b2344); base, size, n = u32(first, obj + 0x20), u32(first, obj + 0x10), u32(first, obj + 0x18)
    raw = H.readmem(first, base, size * n)
    idx = next(i for i in range(n) if struct.unpack_from('<H', raw, i * size + 0x28)[0] == emp)
for x, pid in P.items():
    if idx is not None:
        obj = u32(pid, 0x5b2344); base, size = u32(pid, obj + 0x20), u32(pid, obj + 0x10)
        a = base + idx * size
        assert struct.unpack('<H', H.readmem(pid, a + 0x28, 2))[0] == emp, x
        H.writemem(pid, a + 0x52, struct.pack('<H', old))
    if H.readmem(pid, 0x69e000, 4) is None:
        raise SystemExit('no test shim section in %s' % x)
    H.writemem(pid, STUB, code)
    H.writemem(pid, PAR, struct.pack('<IIII', 1, emp, old, new))
    H.writemem(pid, 0x453824, call_rel(0x453824, STUB))
    print(x, 'armed: refit emp %d class %d -> %d%s' % (emp, old, new, '' if idx is None else ', ship #%d made class %d' % (idx, old)))
