"""Fix F test: set bit 0 of +0x364 of every monster combat unit (type 7) in the running combat of one instance,
like a leftover heap byte on that machine. usage: monpoke.py <inst> [0|1]   (default 1; prints the units)"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
inst = sys.argv[1]; val = int(sys.argv[2]) if len(sys.argv) > 2 else 1
pid = H.load_state()[inst]
u32 = lambda a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
arr, n = u32(0x597864), u32(0x602b14)
print(inst, 'units', n, 'array', hex(arr))
for i in range(n if arr else 0):
    e = arr + i * 0x3c8
    typ = struct.unpack('<h', H.readmem(pid, e + 0x178, 2))[0]
    owner = H.readmem(pid, e + 0x1dc, 1)[0]
    f = H.readmem(pid, e + 0x364, 1)[0]
    print(' unit %d type %d owner %#x +0x364=%#x' % (i, typ, owner, f))
    if typ == 7:
        H.writemem(pid, e + 0x364, bytes([(f & ~1) | val]))
        print('   -> set to', (f & ~1) | val)
