"""Compare the order lists of both instances by content (type, emp, gen, body), ignoring sequence
numbers, which legitimately differ between machines. Returns a list of difference strings."""
import collections, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

def orders(pid):
    u = lambda a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
    tbl = H.readmem(pid, 0x590250, 10 * 0xc)
    size = {i: struct.unpack_from('<I', tbl, i * 0xc)[0] for i in range(10)}
    node = u(u(0x59024c)); out = []
    while node and len(out) < 100000:
        h = H.readmem(pid, node + 8, 0x18)
        sq, gen, emp = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]; bp = struct.unpack_from('<I', h, 0x14)[0]
        n = size.get(ty, 0) if 0 <= ty < 10 else 0
        body = H.readmem(pid, bp, n) if bp and n else b''
        if ty == 0 and len(body) > 0x17:
            body = body[:0x17] + bytes(1) + body[0x18:]   # uninitialised byte of local_18 in FUN_00463980
        out.append((ty, emp, gen, body, sq)); node = u(node)
    return out

def compare(pa, pb):
    a, b = orders(pa), orders(pb)
    # type 9 requests are local until sent and differ by design (each machine tags its own empire)
    ca = collections.Counter(o[:4] for o in a if o[0] != 9)
    cb = collections.Counter(o[:4] for o in b if o[0] != 9)
    rep = []
    for k, v in (ca - cb).items():
        rep.append('order only on A x%d: type %d emp %d gen %d body %s' % (v, k[0], k[1], k[2], k[3].hex()[:40]))
    for k, v in (cb - ca).items():
        rep.append('order only on B x%d: type %d emp %d gen %d body %s' % (v, k[0], k[1], k[2], k[3].hex()[:40]))
    return rep, len(a), len(b)

if __name__ == '__main__':
    st = H.load_state()
    rep, na, nb = compare(st['A'], st['B'])
    print('orders A %d B %d, differences %d' % (na, nb, len(rep)))
    for r in rep[:20]: print('  ', r)
