"""Observer for two independent player agents (tools/player.py): keeps both games active, traces
order kills (ktrace) in both, and the moment each game reaches a new turn it snapshots state, RNG and
heartbeat CRCs; once both are there it compares them. Stops everything (writes <logdir>/stop) at a
heartbeat mismatch, a dead game, an eliminated player, no progress for 5 minutes, or after <turns>.
usage: observer.py <turns> <logdir>"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
import ordercmp
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, snapshot, compare, force_active, screen

HERE = os.path.dirname(os.path.abspath(__file__))
n, out = int(sys.argv[1]), sys.argv[2]
os.makedirs(out, exist_ok=True)
st = H.load_state(); NAMES = [k for k in 'ABCDE' if k in st and H.pid_alive(st[k])]; P = {k: st[k] for k in NAMES}
LOG = open(os.path.join(out, 'observer.log'), 'a')


def log(*a):
    s = '%s %s' % (time.strftime('%H:%M:%S'), ' '.join(str(x) for x in a))
    print(s); LOG.write(s + '\n'); LOG.flush(); sys.stdout.flush()


stopf = os.path.join(out, 'ktrace.stop')
for f in (stopf, os.path.join(out, 'stop')):
    if os.path.exists(f): os.remove(f)
env = dict(os.environ, TRACER_STOP=stopf, ONLY2='1')
tr = [subprocess.Popen([sys.executable, '-I', '-u', os.path.join(HERE, 'ktrace.py'), str(P[x]), '86400'],
                       stdout=open(os.path.join(out, 'ktrace_%s.log' % x), 'a'), stderr=subprocess.STDOUT, env=env) for x in NAMES]
time.sleep(3)
MASK0 = H.readmem(P[NAMES[0]], 0x5a2b28, 1)[0]
start = u32(P[NAMES[0]], TURN_ADDR)
idle = {}
snaps = {}                      # turn -> {inst: snapshot taken when that game became idle at that turn}
seen = {x: u32(P[x], TURN_ADDR) for x in NAMES}
last_progress = time.time(); reason = None; progress_turn = min(seen.values())
LOCAL = {x: H.readmem(P[x], 0x5a2b2a, 1)[0] for x in NAMES}; OUT = {}
log('observer start turn', start, 'mask', hex(MASK0), 'instances', NAMES)
try:
    while True:
        dead = [x for x in NAMES if not H.pid_alive(P[x])]
        if [x for x in dead if x not in OUT]:
            reason = 'dead game: %s' % dead; break
        for x in [x for x in OUT if time.time() - OUT[x] > 120 and x in NAMES]:
            NAMES.remove(x); P.pop(x); seen.pop(x, None)    # eliminated player leaves the comparison
            for t in snaps: snaps[t].pop(x, None)
            log('%s (empire %d) removed after its elimination; remaining %s' % (x, LOCAL[x], NAMES))
        live = [x for x in NAMES if x not in OUT]
        force_active({x: P[x] for x in live})
        masks = {x: H.readmem(P[x], 0x5a2b28, 1)[0] for x in live}
        turns = {x: u32(P[x], TURN_ADDR) for x in live}
        if len(set(masks.values())) > 1:
            reason = 'masks differ between games: %s turns %s' % ({x: hex(m) for x, m in masks.items()}, turns); break
        m = next(iter(masks.values()))
        if m != MASK0:
            gone = [x for x in NAMES if not m & (1 << LOCAL[x]) and x not in OUT]
            log('PLAYER ELIMINATED: mask %#x -> %#x at turns %s, instances %s; watching 120 s for crashes, then continuing' % (MASK0, m, turns, gone))
            for x in gone: OUT[x] = time.time()
            MASK0 = m
            if not gone:
                reason = 'mask changed without a local player leaving: %#x' % m; break
            continue
        if max(turns.values()) - min(turns.values()) > 1:     # lockstep games never drift apart by two turns
            reason = 'games apart: turns %s busy %s' % (turns, {x: i32(P[x], BUSY_ADDR) for x in live}); break
        for x in live:
            t = u32(P[x], TURN_ADDR)
            if t > seen[x] and i32(P[x], BUSY_ADDR) == 0:
                # busy is cleared inside the turn code (0x4586d8) before the heartbeat CRCs are computed
                # (0x458233): only snapshot a game that has been idle for a second
                idle.setdefault((x, t), time.time())
                if time.time() - idle[(x, t)] >= 1.0:
                    snaps.setdefault(t, {})[x] = snapshot(P[x]); seen[x] = t
        if min(seen[x] for x in live) > progress_turn:                 # progress means both games advanced
            progress_turn = min(seen[x] for x in live); last_progress = time.time()
        for t in sorted(list(snaps)):                          # compare each turn once both games reached it
            if any(x not in snaps[t] for x in live):
                continue
            ss = snaps.pop(t); hb = []; line = []
            for x in live[1:]:                                 # every game against the first live one
                rep = compare(ss[live[0]], ss[x])
                hb += ['%s: %s' % (x, r) for r in rep if r.startswith(('RNG differs', 'CRC vars differ', 'turn differs'))]
                line.append('%s %d' % (x, len(rep)))
                for r in rep[:3]:
                    log('    %s%s: %s' % (live[0], x, r[:200]))
            od, na, nb = ordercmp.compare(P[live[0]], P[live[1]])
            if t % 20 == 0 and not hb:                         # checkpoint for tools/resume5.sh
                import shutil
                sd = os.path.join(HERE, '..', 'saves', '%s_t%d' % (os.path.basename(os.path.normpath(out)), t))
                os.makedirs(sd, exist_ok=True)
                for x in live:
                    shutil.copyfile(os.path.join(os.environ.get('BOTF_TEST', os.path.join(HERE, '..', 'test')), x, 'auto.sav'), os.path.join(sd, 'auto_%s.sav' % x))
                log('checkpoint ' + os.path.normpath(sd))
            log('turn %d | state diffs vs %s: %s | orders %d' % (t, live[0], ', '.join(line), na))
            if hb:
                for r in hb: log('    ' + r[:300])
                reason = 'HB MISMATCH at turn %d' % t; break
            if t - start >= n:
                reason = 'done %d turns' % n; break
        if reason:
            break
        if time.time() - last_progress > 300:
            reason = 'stuck (busy %s, turns %s)' % ({x: i32(P[x], BUSY_ADDR) for x in live}, {x: u32(P[x], TURN_ADDR) for x in live})
            for x in live:
                screen(x, P[x], os.path.join('..', out, 'stuck%s_t%d' % (x, seen[x])))
                r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'sampler.py'), x, '3', '50'], capture_output=True, text=True).stdout
                log('  stack sample %s:' % x); log(r)
            break
        time.sleep(0.2)
finally:
    log('STOP:', reason)
    if reason and reason.startswith(('PLAYER ELIMINATED', 'dead game', 'games apart')):
        log('keeping tracers attached 120 s to catch follow-up crashes')
        t1 = time.time()
        while time.time() - t1 < 120:
            dead = [x for x in NAMES if not H.pid_alive(P[x])]
            if dead:
                log('dead now: %s' % dead)
            time.sleep(5)
    open(os.path.join(out, 'stop'), 'w').close()                # players keep playing until here
    open(stopf, 'w').close(); time.sleep(5)
    for p in tr:
        try: p.wait(10)
        except Exception: pass
