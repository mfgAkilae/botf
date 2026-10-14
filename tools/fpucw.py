"""Sample the x87 control word of the main thread of both instances.
usage: fpucw.py [seconds] [interval_ms]"""
import collections, ctypes, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from dbg import WOW64_CONTEXT, k32
from sampler import threads

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 2
iv = float(sys.argv[2]) / 1000 if len(sys.argv) > 2 else 0.02
st = H.load_state()
ths = {}
for n in 'AB':
    tid = threads(st[n])[0]
    ths[n] = k32.OpenThread(0x1F03FF, False, tid)
cnt = {n: collections.Counter() for n in 'AB'}
t0 = time.time()
while time.time() - t0 < secs:
    for n, th in ths.items():
        k32.SuspendThread(th)
        ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10008
        k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
        k32.ResumeThread(th)
        cw = struct.unpack_from('<I', bytes(ctx.FloatSave), 0)[0] & 0xffff
        cnt[n]['%04x' % cw] += 1
    time.sleep(iv)
for n in 'AB':
    print(n, dict(cnt[n]))
