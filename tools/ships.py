"""List ship classes per owner and the ship production orders of an empire.
usage: ships.py <inst> [emp]"""
import collections, struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
u32 = lambda pid, a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
x = sys.argv[1]; emp = int(sys.argv[2]) if len(sys.argv) > 2 else None
pid = H.load_state()[x]
obj = u32(pid, 0x5b2344); base, size, n = u32(pid, obj + 0x20), u32(pid, obj + 0x10), u32(pid, obj + 0x18)
raw = H.readmem(pid, base, size * n)
c = collections.Counter()
for i in range(n):
    own, cls = struct.unpack_from('<H', raw, i * size + 0x28)[0], struct.unpack_from('<H', raw, i * size + 0x52)[0]
    if emp is None or own == emp:
        c[(own, cls)] += 1
print('ships (owner, class): count', dict(sorted(c.items())))
lst = u32(pid, 0x59024c); node = u32(pid, lst)
while node:
    h = H.readmem(pid, node + 8, 0x18); sq, gen, e = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]
    bp = struct.unpack_from('<I', h, 0x14)[0]; body = H.readmem(pid, bp, 0x1c) if bp else b''
    if ty == 0 and (emp is None or e == emp) and body[:4] == bytes(4) and body[0x10:0x14] == b'\x03\x00\x00\x00':
        print('ship order seq %08x gen %d emp %d sys %d class %d' % (sq, gen, e, struct.unpack_from('<H', body, 4)[0], struct.unpack_from('<h', body, 0x14)[0]))
    node = u32(pid, node)
