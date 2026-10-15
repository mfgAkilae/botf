"""Count which order types the games create, without a debugger: polls the order list [0x59024c] of every
running instance and records each new order once (seqno, empire, type, first body dword).
usage: orderwatch.py <seconds> [inst]   prints counts per (empire, type, sub) and one sample body per kind"""
import collections, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

dur = float(sys.argv[1]); only = sys.argv[2] if len(sys.argv) > 2 else None
st = H.load_state(); P = {k: st[k] for k in 'ABCDE' if k in st and H.pid_alive(st[k]) and (not only or k == only)}
u = lambda pid, a: struct.unpack('<I', H.readmem(pid, a, 4))[0]
seen = set(); cnt = collections.Counter(); sample = {}
t0 = time.time()
while time.time() - t0 < dur:
    for x, pid in P.items():
        try:
            node = u(pid, u(pid, 0x59024c)); n = 0
            while node and n < 20000:
                h = H.readmem(pid, node + 8, 0x18); sq, gen, e = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]
                bp = struct.unpack_from('<I', h, 0x14)[0]
                if (x, sq, ty) not in seen:
                    seen.add((x, sq, ty))
                    body = H.readmem(pid, bp, 0x20) if bp else b''
                    k = (e, ty, struct.unpack_from('<I', body, 0)[0] if body else -1)
                    cnt[k] += 1; sample.setdefault(k, body.hex())
                node = u(pid, node); n += 1
        except OSError:
            pass
    time.sleep(0.3)
for k in sorted(cnt):
    print('emp %d type %d sub %d: %d   e.g. %s' % (k[0], k[1], k[2], cnt[k], sample[k]))
