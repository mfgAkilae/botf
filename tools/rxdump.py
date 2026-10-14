"""Dump the DPMP receive packet list [0x5a0dfc] of one instance (packets not yet taken by the game)."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

inst = sys.argv[1]
pid = H.load_state()[inst]
u32 = lambda a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
lst = u32(0x5a0dfc)
head, cnt = u32(lst), u32(lst + 4)
print('list', hex(lst), 'head', hex(head), 'count', cnt)
node = head
for i in range(min(cnt, 200)):
    if not node:
        break
    size, data = u32(node + 8), u32(node + 12)
    hdr = struct.unpack('<11I', H.readmem(pid, data, 0x2c))
    body = H.readmem(pid, data + 0x2e, min(16, max(0, size - 0x2e))) if size > 0x2e else b''
    print('%3d node %08x size %4d hdr %s body %s' % (i, node, size, ' '.join('%x' % h for h in hdr), body.hex()))
    node = u32(node)
