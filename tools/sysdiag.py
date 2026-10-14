"""Production state of one system on every running instance: record +0x80..+0xa7, build queue (+0xa8,
0x6c bytes), invested industry, crcSolarBld block and the type-0 production orders for that system.
usage: sysdiag.py <sysidx> [inst ...]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32

idx = int(sys.argv[1])
st = H.load_state()
names = sys.argv[2:] or [k for k in 'ABCDE' if k in st and H.pid_alive(st[k])]
for k in names:
    p = st[k]
    s = H.readmem(p, u32(p, 0x5a36c8) + idx * 0x328, 0x328)
    q = struct.unpack_from('<I', s, 0xa8)[0]
    qd = H.readmem(p, q, 0x6c) if q else b''
    print('%s turn %d busy %d sys %d %s owner %d' % (k, u32(p, 0x5a2918), struct.unpack('<i', H.readmem(p, 0x5a291c, 4))[0], idx,
          s[8:0x28].split(b'\0')[0].decode(), s[0x4c]))
    print('   rec80 %s | last94 %s' % (s[0x80:0x94].hex(), s[0x94:0xa8].hex()))
    print('   queue %s' % ' '.join(qd[i:i + 0xc].hex() for i in range(0, len(qd), 0xc)))
    print('   blk298 %s' % s[0x298:0x2f0].hex())
    lst = u32(p, 0x59024c); node = u32(p, lst)
    while node:
        h = H.readmem(p, node + 8, 0x18); sq, gen, emp = struct.unpack_from('<IIH', h); ty = struct.unpack_from('<i', h, 0x10)[0]
        bp = struct.unpack_from('<I', h, 0x14)[0]
        if ty == 0 and bp:
            b = H.readmem(p, bp, 0x34)
            if struct.unpack_from('<h', b, 4)[0] == idx:
                print('   order seq %08x gen %d emp %d body %s' % (sq, gen, emp, b[:0x18].hex()))
        node = u32(p, node)
