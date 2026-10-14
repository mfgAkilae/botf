"""Drift test: play turns without UI, shift order seqno counters on B (as they drift apart in long
games), keep playing with kill-request tracing; report heartbeat mismatches and remote kills that hit
an existing order (a correct processing request should always find nothing on the receiver).
usage: drift.py <turns_before> <turns_after> <global_delta> [human_delta]"""
import os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, snapshot, compare
HERE = os.path.dirname(os.path.abspath(__file__)); TL = os.path.join(HERE, '..', 'turnlog')
st = H.load_state(); P = {'A': st['A'], 'B': st['B']}
nb, na, gd = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
hd = int(sys.argv[4]) if len(sys.argv) > 4 else 0
LOG = open(os.path.join(TL, 'drift.log'), 'a')
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n'); LOG.flush(); sys.stdout.flush()
def counters(n):
    return list(struct.unpack('<6I', H.readmem(P[n], 0x590230, 24)))
def turn(trace):
    stopf = os.path.join(TL, 'drift.stop'); t = u32(P['A'], 0x5a2918)
    if trace:
        if os.path.exists(stopf): os.remove(stopf)
        env = dict(os.environ, TRACER_STOP=stopf, ONLY2='1')
        for n in 'AB':
            subprocess.Popen([sys.executable, '-I', '-u', os.path.join(HERE, 'ktrace.py'), str(P[n]), '900'],
                             stdout=open(os.path.join(TL, 'd_t%03d_%s.log' % (t, n)), 'w'), stderr=subprocess.STDOUT, env=env)
        time.sleep(2.5)
    r = subprocess.run([sys.executable, '-I', '-u', os.path.join(HERE, 'autoturn.py'), '1'], capture_output=True, text=True).stdout
    if trace:
        open(stopf, 'w').close(); time.sleep(3)
    line = [l for l in r.splitlines() if l.startswith('turn')]
    rep = compare(snapshot(P['A']), snapshot(P['B']))
    hb = [x for x in rep if x.startswith(('RNG', 'CRC', 'turn differs'))]
    hits = []
    if trace:
        for n in 'AB':
            txt = open(os.path.join(TL, 'd_t%03d_%s.log' % (t, n))).read()
            hits += ['%s: %s' % (n, l.strip()) for l in txt.splitlines() if '-> matched' in l]
    log('turn %d: %s | state diffs %d | heartbeat %s | remote kills that hit an order: %d' % (t, line[-1] if line else 'no result', len(rep), 'MISMATCH' if hb else 'ok', len(hits)))
    for h in hits: log('    ' + h)
    for x in hb: log('    ' + x)
    return bool(hb) or not line or 'ok' not in line[-1]

log('=== drift test exe=%s before=%d after=%d global_delta=%d human_delta=%d' % (open(os.path.join(os.environ.get('BOTF_TEST', os.path.join(HERE, '..', 'test')), 'A', 'trek.exe'), 'rb').read()[0x56d46:0x56d4c].hex(), nb, na, gd, hd))
for i in range(nb):
    if turn(False): sys.exit(1)
ca, cb = counters('A'), counters('B')
log('counters A', ' '.join('%x' % c for c in ca)); log('counters B', ' '.join('%x' % c for c in cb))
cb[5] = (cb[5] + gd) & 0xffffffff
if hd:
    # B's copy of A's empire counter and A's copy of B's empire counter move by hd
    cb[0] = (cb[0] + hd) & 0xffffffff
H.writemem(P['B'], 0x590230, struct.pack('<6I', *cb))
log('B counters shifted ->', ' '.join('%x' % c for c in counters('B')))
for i in range(na):
    if turn(True):
        log('STOP: heartbeat mismatch or turn failure'); sys.exit(2)
log('done: no heartbeat mismatch')
