"""Fix RY abort paths while the host waits for ACKs. Five instances: A..D run an RY build, <old> runs one without
(resume with EXE_<old>=...), so the host never gets every ACK and stays in its 30 s ACK wait. A divergence is poked
on client C and one turn is played until the host has sent ARM.
  session  the host's in-game flag [0x5a2920] is cleared for 3 s (as when the player leaves the session): the host
           must abort with F_SESSION (11) and neither send nor load; the clients stay ARMED until the host's CANCEL
           never comes and the ARM wait or the host check ends it (not checked here)
  kill     the host's game is killed: every client must end its ARMED state without a load once the host's entry
           is gone from the player table (F_HOSTGONE, 12)
usage: ryabort.py <exe> <old> session|kill"""
import json, os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import i32, u32, force_active

EXE, OLD, MODE = sys.argv[1], sys.argv[2], sys.argv[3]
F = json.load(open(EXE + '.json'))['spike']
st = H.load_state(); P = {k: st[k] for k in 'ABCDE'}
NEW = [k for k in P if k != OLD]
HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ('sp_state', 'sp_auto', 'sp_auto_n', 'sp_arm_rx', 'ack_mask', 'cnt_applies', 'last_fail', 'cnt_cancel',
        'sp_fallback', 'rs_guard', 'cnt_session')
CLOSE = {'A': [(400, 386)], 'B': [(305, 266)], 'C': [(236, 344)], 'D': [(300, 336), (232, 252)], 'E': [(210, 292)]}


def fields(x):
    return {k: i32(P[x], F[k]) for k in KEYS}


sp = u32(P['C'], 0x5a36c8) + 5 * 0x328 + 0x2dc
v = struct.unpack('<h', H.readmem(P['C'], sp, 2))[0]
H.writemem(P['C'], sp, struct.pack('<h', v + 7))
applies0 = {x: fields(x)['cnt_applies'] for x in NEW}
r = subprocess.Popen([sys.executable, '-I', os.path.join(HERE, 'turn5.py')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
t0 = time.time()
while time.time() - t0 < 120 and fields('A')['sp_auto'] != 2:
    force_active(P); time.sleep(0.2)
r.kill()
print('host waits for ACKs after %.0fs' % (time.time() - t0), {x: fields(x) for x in NEW}, flush=True)
checks = {'host sent ARM': fields('A')['sp_auto_n'] == 1}
if MODE == 'session':
    H.writemem(P['A'], 0x5a2920, struct.pack('<i', 0))
    time.sleep(3)
    a = fields('A')
    H.writemem(P['A'], 0x5a2920, struct.pack('<i', 1))
    print('host after 3 s outside the game', a, flush=True)
    time.sleep(35)                                   # past the ACK wait: nothing may be sent any more
    fin = {x: fields(x) for x in NEW}
    print('35 s later', fin, flush=True)
    checks.update({
        'host aborted with F_SESSION': a['last_fail'] == 11 and a['sp_state'] == 0,
        'host session state cleared': a['cnt_session'] >= 1,
        'host sent no CANCEL and loaded nothing': fin['A']['cnt_cancel'] == 0 and fin['A']['cnt_applies'] == applies0['A'],
        'no client loaded anything': all(fin[x]['cnt_applies'] == applies0[x] for x in NEW),
    })
else:
    subprocess.run(['taskkill', '/PID', str(P['A']), '/F'], capture_output=True)
    REST = [x for x in NEW if x != 'A']
    t1 = time.time()
    while time.time() - t1 < 240 and not all(fields(x)['sp_state'] == 0 for x in REST):
        for x in REST:
            if i32(P[x], 0x5a291c) != 1:
                for xy in CLOSE[x]:
                    H.click(H.main_window(P[x]), *xy, pid=P[x])
        time.sleep(3)
    fin = {x: fields(x) for x in REST}
    print('after %.0fs' % (time.time() - t1), fin, flush=True)
    checks.update({
        'every client left ARMED': all(fin[x]['sp_state'] == 0 and fin[x]['rs_guard'] == 0 for x in REST),
        'because the host is gone (F_HOSTGONE)': all(fin[x]['last_fail'] == 12 for x in REST),
        'well before the 300 s ARM wait': time.time() - t1 < 200,
        'no client loaded anything': all(fin[x]['cnt_applies'] == applies0[x] for x in REST),
    })
for k, ok in checks.items():
    print('  %-45s %s' % (k, 'ok' if ok else 'FAIL'))
print('RESULT', 'PASS' if all(checks.values()) else 'FAIL')
sys.exit(0 if all(checks.values()) else 1)
