"""Fix RY with a player who does not have it: instances A..D run a build with the automatic resync, <old> runs one
without (resume with EXE_<old>=...). A divergence is poked on client <x> (morale word +0x2dc of system <s>), then
turns are played as tools/turn5.py does. Expected: the host detects the mismatch and sends ARM; the old build
ignores ARM and never answers; after ACK_WAIT_MS the host sends CANCEL, every machine with the fix ends the transfer
without loading and shows the stock synchronization error at its next mismatch (the behaviour without the fix).
The fields are read with the layout of <exe>.json (A..D).
usage: rymixed.py <exe> <old> <x> <s>"""
import json, os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import i32, u32, force_active

EXE, OLD, X, SYS = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
F = json.load(open(EXE + '.json'))['spike']
st = H.load_state(); P = {k: st[k] for k in 'ABCDE'}
NEW = [k for k in P if k != OLD]
HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ('sp_state', 'sp_detect', 'sp_fallback', 'sp_auto_n', 'sp_arm_rx', 'cnt_cancel', 'cnt_ackrx', 'ack_mask',
        'ack_need', 'last_fail', 'cnt_applies', 'cnt_mismatch')


def fields(x):
    return {k: i32(P[x], F[k]) for k in KEYS}


def stock_box(pid):
    """the stock mismatch box FUN_005004a4 on the main thread's stack (return 0x5100e9 or 0x51033f), as tools/spike.py"""
    import ctypes
    from dbg import WOW64_CONTEXT, k32, rpm
    from sampler import threads
    hp = k32.OpenProcess(0x1F0FFF, False, pid); th = k32.OpenThread(0x1F03FF, False, threads(pid)[0])
    try:
        k32.SuspendThread(th)
        ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
        k32.Wow64GetThreadContext(th, ctypes.byref(ctx)); stk = rpm(hp, ctx.Esp, 0x2000)
    finally:
        k32.ResumeThread(th); k32.CloseHandle(th); k32.CloseHandle(hp)
    return any(struct.unpack_from('<I', stk, o)[0] in (0x5100e9, 0x51033f) for o in range(0, len(stk) - 3, 4))


def boxes():
    return [x for x in P if H.pid_alive(P[x]) and stock_box(P[x])]


sp = u32(P[X], 0x5a36c8) + SYS * 0x328 + 0x2dc
v = struct.unpack('<h', H.readmem(P[X], sp, 2))[0]
H.writemem(P[X], sp, struct.pack('<h', v + 7))
print('poked %s system %d morale %d -> %d' % (X, SYS, v, v + 7), flush=True)
t0 = time.time(); applies0 = {x: fields(x)['cnt_applies'] for x in NEW}
r = subprocess.Popen([sys.executable, '-I', os.path.join(HERE, 'turn5.py')], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
while r.poll() is None and time.time() - t0 < 300:
    force_active(P)
    if OLD in boxes():
        print('stock error box on %s after %.0fs (expected: it has no resync)' % (OLD, time.time() - t0), flush=True)
        r.kill(); break
    time.sleep(1)
# the host keeps waiting for the old player's ACK; it cancels after ACK_WAIT_MS
while time.time() - t0 < 300 and not (i32(P['A'], F['cnt_cancel']) > 0 and all(fields(x)['sp_state'] == 0 for x in NEW)):
    force_active(P); time.sleep(1)
fin = {x: fields(x) for x in NEW}
print('after %.0fs' % (time.time() - t0), fin, flush=True)
checks = {
    'old player shows the stock error': OLD in boxes(),
    'host sent ARM once': fin['A']['sp_auto_n'] == 1,
    'host cancelled (ACK timeout)': fin['A']['cnt_cancel'] == 1 and fin['A']['last_fail'] == 9,
    'old player missing in the ACK mask': fin['A']['ack_need'] == 1 << H.readmem(P[OLD], 0x5a2b2a, 1)[0],
    'every new client took the CANCEL': all(fin[x]['cnt_cancel'] == 1 and fin[x]['last_fail'] == 10 for x in NEW if x != 'A'),
    'all idle with the stock fallback': all(fin[x]['sp_state'] == 0 and fin[x]['sp_fallback'] == 1 for x in NEW),
    'nothing loaded': all(fin[x]['cnt_applies'] == applies0[x] for x in NEW),
    'new players show no box': not [x for x in boxes() if x != OLD],
}
for k, v in checks.items():
    print('  %-40s %s' % (k, 'ok' if v else 'FAIL'))
print('RESULT', 'PASS' if all(checks.values()) else 'FAIL')
sys.exit(0 if all(checks.values()) else 1)
