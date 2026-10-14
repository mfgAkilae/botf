"""Dump the order list [0x59024c] of both instances and compare (by content, ignoring seqno).
usage: orders.py [-v]"""
import collections, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
SIZES = {}
def table(pid):
    t = H.readmem(pid, 0x590250, 10 * 0xc)
    return {i: struct.unpack_from('<I', t, i * 0xc)[0] for i in range(10)}

def dump(pid):
    u = lambda a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
    sz = table(pid)
    lst = u(0x59024c); node = u(lst); out = []
    while node and len(out) < 50000:
        h = H.readmem(pid, node + 8, 0x18)
        sq, gen, emp = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]; bp = struct.unpack_from('<I', h, 0x14)[0]
        n = sz.get(ty, 0) if 0 <= ty < 10 else 0
        body = H.readmem(pid, bp, n) if bp and n else b''
        out.append((sq, gen, emp, ty, body))
        node = u(node)
    ctr = struct.unpack('<6I', H.readmem(pid, 0x590230, 24))
    return out, ctr

st = H.load_state()
res = {n: dump(st[n]) for n in 'AB'}
for n in 'AB':
    print(n, 'orders', len(res[n][0]), 'counters', ' '.join('%x' % c for c in res[n][1]))
ca = collections.Counter((g, e, t, b) for s, g, e, t, b in res['A'][0])
cb = collections.Counter((g, e, t, b) for s, g, e, t, b in res['B'][0])
print('content only in A:', sum((ca - cb).values()), ' only in B:', sum((cb - ca).values()))
for k, v in list((ca - cb).items())[:10]: print('  A-only', k[:3], k[3].hex()[:48], v)
for k, v in list((cb - ca).items())[:10]: print('  B-only', k[:3], k[3].hex()[:48], v)
# same content, different seqno
sa = {}; [sa.setdefault((g, e, t, b), []).append(s) for s, g, e, t, b in res['A'][0]]
sb = {}; [sb.setdefault((g, e, t, b), []).append(s) for s, g, e, t, b in res['B'][0]]
diffseq = [(k, sa[k], sb[k]) for k in sa if k in sb and sorted(sa[k]) != sorted(sb[k])]
print('same content, different seqno:', len(diffseq))
for k, a, b in diffseq[:15]:
    print('   gen %d emp %d type %d  A %s  B %s' % (k[0], k[1], k[2], [hex(x) for x in a], [hex(x) for x in b]))
if '-v' in sys.argv:
    for n in 'AB':
        print('==', n)
        for s, g, e, t, b in res[n][0]: print('  %08x gen %3d emp %3d type %d %s' % (s, g, e, t, b.hex()[:40]))
