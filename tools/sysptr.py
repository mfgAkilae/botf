"""Dump the heap blocks behind the pointers at system+0xa8..0xb8 for one system on both instances and diff them.
usage: sysptr.py <system name> [len]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

name = sys.argv[1].encode(); n = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x200
st = H.load_state(); res = {}
for inst in 'AB':
    pid = st[inst]
    sp = struct.unpack('<I', H.readmem(pid, 0x5a36c8, 4))[0]
    cnt = struct.unpack('<H', H.readmem(pid, 0x5a36bc, 2))[0]
    for i in range(cnt):
        s = H.readmem(pid, sp + i * 0x328, 0x328)
        if s[8:0x30].split(b'\0')[0] == name:
            blocks = {}
            for off in (0xa8, 0xac, 0xb0, 0xb4, 0xb8):
                p = struct.unpack_from('<I', s, off)[0]
                try:
                    blocks[off] = H.readmem(pid, p, n) if p else b''
                except OSError:
                    blocks[off] = b'?'
            res[inst] = blocks
for off in (0xa8, 0xac, 0xb0, 0xb4, 0xb8):
    a, b = res['A'][off], res['B'][off]
    d = [o for o in range(min(len(a), len(b))) if a[o] != b[o]]
    print('+%#x' % off, 'len', len(a), 'diff bytes', len(d), 'first', [hex(x) for x in d[:12]])
    if '-v' in sys.argv:
        print('   A', a[:0x80].hex()); print('   B', b[:0x80].hex())
