"""Fix RY after a host migration: the host A has already run one transfer (every machine holds its epoch), then A's
game is killed; DirectPlay makes another machine the host ([0x5fd978] = 1). A divergence is poked on a remaining
client and turns are played (tools/turn5.py). Expected: the new host detects the mismatch, sends ARM with its own
epoch, gets ACK from every remaining player (A is no longer in the player mask) and transfers; the clients accept
the new host's ARM although its epoch may equal the one they took from A (a transfer is identified by epoch and
sender). Run on five instances of an RY build resumed from a five-human save.
usage: rymigrate.py <exe> <system>"""
import json, os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import i32, u32, force_active

EXE, SYS = sys.argv[1], int(sys.argv[2])
F = json.load(open(EXE + '.json'))['spike']
st = H.load_state(); P = {k: st[k] for k in 'ABCDE'}
HERE = os.path.dirname(os.path.abspath(__file__))
CLOSE = {'A': [(400, 386)], 'B': [(305, 266)], 'C': [(236, 344)], 'D': [(300, 336), (232, 252)], 'E': [(210, 292)]}
KEYS = ('sp_state', 'sp_epoch', 'arm_sender', 'sp_auto_n', 'sp_arm_rx', 'cnt_ackrx', 'ack_mask', 'cnt_applies',
        'sp_fallback', 'cnt_cancel', 'last_result')


def fields(x):
    return {k: i32(P[x], F[k]) for k in KEYS}


def poke(x):
    sp = u32(P[x], 0x5a36c8) + SYS * 0x328 + 0x2dc
    v = struct.unpack('<h', H.readmem(P[x], sp, 2))[0]
    H.writemem(P[x], sp, struct.pack('<h', v + 7))
    print('poked %s system %d morale %d -> %d' % (x, SYS, v, v + 7), flush=True)


ADVANCED = []                  # (turn before, turns after) of every turn5.py run


def turns(names, n, until=None):
    for _ in range(n):
        t0 = {x: u32(P[x], 0x5a2918) for x in names}
        r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'turn5.py')], capture_output=True, text=True, timeout=600)
        print('\n'.join(l[:170] for l in r.stdout.splitlines() if l.startswith(('turn', 'timeout', 'Traceback', 'Assertion')) or 'MISMATCH' in l), flush=True)
        ok = r.returncode == 0 and 'timeout' not in r.stdout and all(u32(P[x], 0x5a2918) > t0[x] for x in names)
        ADVANCED.append(ok)
        if not ok:
            print('turn did not advance on every instance', {x: (t0[x], u32(P[x], 0x5a2918)) for x in names}, flush=True)
        if until and until():
            return


def wait_idle(names, t=240):
    t0 = time.time()
    while time.time() - t0 < t and not all(fields(x)['sp_state'] == 0 for x in names):
        force_active({x: P[x] for x in names}); time.sleep(1)


# 1 a transfer with A as host: every machine takes A's epoch
poke('C')
turns('ABCDE', 2, until=lambda: fields('A')['sp_auto_n'] >= 1)
wait_idle('ABCDE')
print('after the first transfer', {x: fields(x) for x in 'ABCDE'}, flush=True)
# 2 the host leaves
subprocess.run(['taskkill', '/PID', str(P['A']), '/F'], capture_output=True)
REST = 'BCDE'
t0 = time.time()
while time.time() - t0 < 180 and not any(u32(P[x], 0x5fd978) == 1 for x in REST):
    time.sleep(2)
host = [x for x in REST if u32(P[x], 0x5fd978) == 1]
print('new host %s after %.0fs' % (host, time.time() - t0), flush=True)
t0 = time.time()
while time.time() - t0 < 150 and any(H.readmem(P[x], 0x5a2b28, 1)[0] & 1 for x in REST):
    for x in REST:
        if i32(P[x], 0x5a291c) != 1:
            for xy in CLOSE[x]:
                H.click(H.main_window(P[x]), *xy, pid=P[x])
    time.sleep(5)
for _ in range(3):
    for x in REST:
        for xy in CLOSE[x]:
            H.click(H.main_window(P[x]), *xy, pid=P[x])
    time.sleep(3)
print('masks', {x: hex(H.readmem(P[x], 0x5a2b28, 1)[0]) for x in REST}, flush=True)
del P['A']
st['A'] = 0
turns(REST, 1)
# 3 a divergence on a client of the new host
victim = [x for x in REST if x not in host][0]
n0 = fields(host[0])['sp_auto_n'] if host else 0
poke(victim)
turns(REST, 3, until=lambda: host and fields(host[0])['sp_auto_n'] > n0)
wait_idle(REST)
fin = {x: fields(x) for x in REST}
print('final', fin, flush=True)
n_after = len(ADVANCED)
turns(REST, 2)
crc = {x: H.readmem(P[x], 0x597610, 10).hex() for x in REST}
checks = {
    'a new host': len(host) == 1,
    'new host started one transfer': bool(host) and fin[host[0]]['sp_auto_n'] == n0 + 1,
    'every client applied twice (A, then the new host)': all(fin[x]['cnt_applies'] == 2 for x in REST),
    'no fallback, no cancel': all(fin[x]['sp_fallback'] == 0 and fin[x]['cnt_cancel'] == 0 for x in REST),
    'two more turns played on every instance': len(ADVANCED) == n_after + 2 and all(ADVANCED[n_after:]),
    'checksum words equal two turns later': len(set(crc.values())) == 1,
}
for k, v in checks.items():
    print('  %-50s %s' % (k, 'ok' if v else 'FAIL'))
print('RESULT', 'PASS' if all(checks.values()) else 'FAIL')
sys.exit(0 if all(checks.values()) else 1)
