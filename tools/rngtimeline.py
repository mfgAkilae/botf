"""End the turn on every instance and record the normalised main RNG (the block the 0x71 compares) of every
instance every 0.25 s until all are idle again plus <tail> seconds. Shows whether the RNG changes on an idle machine
after its turn end (a late 0x71 is compared at once on an idle receiver, 0x510487).
usage: rngtimeline.py [tail_s]"""
import os, struct, sys, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state()
N = [k for k in 'ABCDE' if k in st and H.pid_alive(st[k])]
tail = float(sys.argv[1]) if len(sys.argv) > 1 else 30


def rd(x, a, n):
    return H.readmem(st[x], a, n)


def snap(x):
    r = bytearray(rd(x, 0x596bac, 0x120))
    r[4:0x18] = bytes(0x14)
    return (struct.unpack('<I', rd(x, 0x5a2918, 4))[0], struct.unpack('<i', rd(x, 0x5a291c, 4))[0], zlib.crc32(bytes(r)) & 0xffff)


t0 = time.time()
turn0 = snap(N[0])[0]
for x in N:
    hw = H.main_window(st[x])
    H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.4)
    H.click(hw, *TURN[x], pid=st[x])
last, idle_since = None, None
while True:
    s = {x: snap(x) for x in N}
    now = time.time() - t0
    line = ' '.join('%s:%d/%2d/%04x' % (x, *s[x]) for x in N)
    if line != last:
        print('%6.2f %s' % (now, line)); sys.stdout.flush()
        last = line
    if all(v[0] > turn0 and v[1] == 0 for v in s.values()):
        idle_since = idle_since or now
        if now - idle_since > tail:
            break
    if now > 300:
        print('timeout'); break
    time.sleep(0.25)

# a sync-error box of the incoming 0x71 compare (0x51031f -> FUN_005004a4, return 0x51033f) on any machine?
import ctypes
from dbg import WOW64_CONTEXT, k32, rpm
from sampler import threads
for x in N:
    hp = k32.OpenProcess(0x1F0FFF, False, st[x]); th = k32.OpenThread(0x1F03FF, False, threads(st[x])[0])
    k32.SuspendThread(th); ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
    k32.Wow64GetThreadContext(th, ctypes.byref(ctx)); stk = rpm(hp, ctx.Esp, 0x1000); k32.ResumeThread(th)
    rets = {struct.unpack_from('<I', stk, i)[0] for i in range(0, len(stk) - 3, 4)}
    if 0x51033f in rets:
        print('SYNC ERROR BOX (incoming 0x71 RNG compare) on', x)
