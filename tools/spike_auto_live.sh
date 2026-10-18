#!/bin/bash
# usage: spike_auto_live.sh <exe> <logdir> <seed> <turns> <savedir> [interval]
# Automatic resync under play: resume <savedir> with <exe> (a --spike build with the automatic path), start the
# observer (<logdir>) and five player agents (<logdir>/agents, player.py --spike-json: no input while a transfer
# runs). Every <interval> turns (default 4), between two turns, add 7 to the morale of one system of a random client:
# the next heartbeat compare mismatches and the game must heal itself (host PREPARE -> ARM -> SEND, every client
# applies). The observer pauses (<logdir>/pause) from the injection until the healed turn, it would stop at the
# injected mismatch; the agents pause (<logdir>/agents/pause) from the start of the transfer until the observer has
# compared the healed turn. Injections in <logdir>/inject.log, summary in <logdir>/summary.txt.
cd "$(dirname "$0")/.." || exit 1                 # repository root
EXE=$1; D=$2; SEED=$3; N=$4; SAV=$5; IV=${6:-4}; AG=$D/agents
mkdir -p $AG; rm -f $D/stop $D/pause $AG/stop $AG/pause
export SPIKE_JSON=$EXE.json            # field addresses for tools/spike.py
[ -s $SPIKE_JSON ] || { echo "missing $SPIKE_JSON (build_test.py writes it next to the exe it builds)"; exit 1; }
python -I -c "import sys; sys.path.insert(0, 'tools'); import spike as S; m = [k for k in S.AUTO + ('sp_state', 'rs_guard', 'cnt_applies') if k not in S.F]; sys.exit('%s has no %s: not a build with the automatic resync' % (S.JSON, ', '.join(m)) if m else 0)" || exit 1
R=$(bash tools/resume5.sh $SAV $EXE | tail -1); echo "$R"; echo "$R" | grep -q "^loaded after" || { echo "resume failed"; exit 1; }
sleep 3
nohup python -I -u tools/observer.py $N $D > $D/observer_stdout.txt 2>&1 &
sleep 6
for x in A B C D E; do f=""; [ $x = A ] && f="--heavy"; nohup python -I -u tools/player.py $x $SEED $AG --spike-json $SPIKE_JSON $f $PLAYER_FLAGS > $AG/player_${x}_stdout.txt 2>&1 & sleep 1; done
turn() { python -I -c "import sys,struct; sys.path.insert(0,'tools'); import harness as H; print(struct.unpack('<I', H.readmem(H.load_state()['A'], 0x5a2918, 4))[0])"; }
next=$(( $(turn) + IV )); k=0
while [ ! -e $D/stop ]; do
  until [ "$(turn)" -ge "$next" ] || [ -e $D/stop ]; do sleep 5; done
  [ -e $D/stop ] && break
  k=$((k + 1))
  # exit 0 healed, 2 fallback, 3 transfer not finished, 4 no transfer, 5 stock error box, 6 not healed, 7 no client,
  # 8 observer stopped
  python -I -u - $D $AG $SEED $k <<'EOF' 2>&1 | tee -a $D/inject.log
import os, random, struct, sys, time; sys.path.insert(0, 'tools')
import spike as S                                     # field addresses from $SPIKE_JSON
from autoturn import force_active
D, AG, seed, k = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
host = 'A'; rnd = random.Random(seed * 1000 + k)
turn = lambda x=host: S.u32(x, 0x5a2918)
busy = lambda x: S.i32(x, 0x5a291c)
calm = lambda: all(S.spike_idle(x) for x in S.NAMES)
stop = lambda: os.path.exists(os.path.join(D, 'stop'))
compared = lambda t: ' turn %d |' % t in open(os.path.join(D, 'observer.log')).read()
# 1 between two turns: one turn everywhere, nobody processing, no transfer, past every quiet window, and the observer
#   has compared this turn (the injection must not be part of that compare)
t0 = time.time()
while True:
    if stop():
        print('observer stopped'); sys.exit(8)
    t = turn()
    if (all(turn(x) == t and busy(x) != 1 for x in S.NAMES) and calm() and t > max(S.f(x, 'sp_quiet') - (1 << 32 if S.f(x, 'sp_quiet') >= 1 << 31 else 0) for x in S.NAMES)
            and (compared(t) or time.time() - t0 > 300)):
        break
    time.sleep(1)
mask = S.rd(host, 0x5a2b28, 1)[0]
cl = [x for x in S.NAMES if x != host and (mask >> S.rd(x, 0x5a2b2a, 1)[0]) & 1]
if not cl:
    print('no client left in the game'); sys.exit(7)
v = rnd.choice(cl); emp = S.rd(v, 0x5a2b2a, 1)[0]
sp, n = S.u32(v, 0x5a36c8), struct.unpack('<H', S.rd(v, 0x5a36bc, 2))[0]
raw = S.rd(v, sp, n * 0x328)
si = rnd.choice([i for i in range(n) if raw[i * 0x328 + 0x4c] == emp] or list(range(n)))
c = S.counters()
open(os.path.join(D, 'pause'), 'w').close()
print('=== injection %d at turn %d %s: client %s system %d' % (k, t, time.strftime('%H:%M:%S'), v, si))
S.diverge(v, si, 7, host)
# 2 the next heartbeat compare mismatches: the host must start a transfer and every client apply it
ti = tbox = time.time(); started = late = None
while True:
    if stop():
        print('observer stopped while waiting for the transfer'); sys.exit(8)
    fb = [x for x in S.NAMES if S.f(x, 'sp_fallback') != c[x]['sp_fallback']]
    if fb:
        print('FALLBACK (stock error) on %s' % fb); S.status(); sys.exit(2)
    if S.f(host, 'sp_auto_n') != c[host]['sp_auto_n']:
        if started is None:
            started = time.time()
            open(os.path.join(AG, 'pause'), 'w').close()
            print('transfer started at turn %d, %.0fs after the injection, mismatch detected on %s' % (
                turn(), started - ti, S.detected(c)))
        if calm() and all(S.f(x, 'cnt_applies') != c[x]['cnt_applies'] for x in cl):
            break
        if time.time() - started > 240:
            print('TIMEOUT: transfer not finished after 240s'); S.status(); sys.exit(3)
    else:
        if calm():
            force_active(S.P)
        late = late or (time.time() if turn() >= t + 2 else None)
        if late and time.time() - late > 60 or time.time() - ti > 1200:
            print('no transfer %.0fs after the injection (turn %d -> %d), %s' % (time.time() - ti, t, turn(), S.checksums()))
            S.status(); sys.exit(4)
    if turn() > t and time.time() - tbox > 10:
        box = [x for x in S.NAMES if S.stock_box(x)]; tbox = time.time()
        if box:
            print('STOCK ERROR BOX on %s' % box); S.status(); sys.exit(5)
    time.sleep(0.5)
# 3 healed? checked while the agents hold, then the observer compares this turn before they go on
t1 = time.time()
while not (all(turn(x) == turn() and busy(x) != 1 for x in S.NAMES) and calm()) and time.time() - t1 < 60:
    time.sleep(0.5)
time.sleep(2)
th, cs, s0 = turn(), S.checksums(), S.snapshot(S.P[host])
d = {x: len([r for r in S.compare(s0, S.snapshot(S.P[x])) if not S.owner_records(r)]) for x in S.NAMES if x != host}
box = [x for x in S.NAMES if S.stock_box(x)]
ok = cs == 'checksum words equal' and not any(d.values()) and not box
print('%s at turn %d: applies %s, sp_auto_n %d, %s, state diffs vs %s %s%s, %.0fs after the injection' % (
    'healed' if ok else 'NOT HEALED', th, {x: S.f(x, 'cnt_applies') - c[x]['cnt_applies'] for x in S.NAMES},
    S.f(host, 'sp_auto_n'), cs, host, d, ', STOCK ERROR BOX on %s' % box if box else '', time.time() - ti))
os.remove(os.path.join(D, 'pause'))
t1 = time.time()
while not compared(th) and not stop() and time.time() - t1 < 60:
    time.sleep(1)
os.remove(os.path.join(AG, 'pause'))
sys.exit(0 if ok else 6)
EOF
  rc=${PIPESTATUS[0]}
  [ $rc -eq 8 ] && break
  if [ $rc -ne 0 ]; then
    rm -f $D/pause $AG/pause; touch $AG/stop
    echo "injection $k failed (exit $rc): agents stopped, the observer stops at the mismatch or after 5 minutes without progress" | tee -a $D/inject.log
    break
  fi
  next=$(( $(turn) + IV - 1 ))
done
until [ -e $D/stop ]; do sleep 10; done
touch $AG/stop
python -I - $D $AG <<'EOF' 2>&1 | tee $D/summary.txt
import os, re, sys, time; sys.path.insert(0, 'tools')
import spike as S
D, AG = sys.argv[1], sys.argv[2]
lines = lambda p: open(p, errors='replace').read().splitlines() if os.path.exists(p) else []
inj, obs = lines(os.path.join(D, 'inject.log')), lines(os.path.join(D, 'observer.log'))
stop = [l.split('STOP: ', 1)[1] for l in obs if 'STOP: ' in l]
print('== %s %s, observer: %s' % (D, time.strftime('%Y-%m-%d %H:%M'), stop[-1] if stop else 'no STOP line'))
ni, nh = sum(l.startswith('=== injection') for l in inj), sum(l.startswith('healed') for l in inj)
fails = [l for l in inj if l.startswith(('NOT HEALED', 'FALLBACK', 'TIMEOUT', 'no transfer', 'STOCK', 'injection '))]
print('injections %d, healed %d' % (ni, nh))
for l in inj:
    if l.startswith(('=== injection', 'transfer started', 'healed')) or l in fails:
        print('  ' + l[:220])
print('counters since the resume (host A):%s' % ''.join(' %s dead' % x for x in 'ABCDE' if x not in S.NAMES))
for x in S.NAMES:
    print('  %s sp_auto_n %d  applies %d  fallback %d  arm_rx %d  epoch %d  quiet %d' % (
        x, *(S.f(x, k) for k in ('sp_auto_n', 'cnt_applies', 'sp_fallback', 'sp_arm_rx', 'sp_epoch', 'sp_quiet'))))
if 'A' in S.NAMES:
    a = S.f('A', 'sp_auto_n')
    print('transfers started by the host: %d for %d injections%s' % (
        a, ni, ', %d without an injection (a natural desync?)' % (a - ni) if a > ni else ''))
pend, hb, other, own = [], [], [], 0
for l in obs:
    m = re.match(r'\S+ {5}[A-E]{2}: (.*)', l)
    if m:
        pend.append(m.group(1)); continue
    if re.match(r'\S+ {5}[A-E]: (RNG differs|CRC vars differ|turn differs)', l):
        hb.append(l); continue
    m = re.match(r'\S+ turn (\d+) \| state diffs vs \w: (.*) \| orders', l)
    if m:
        odd = [r for r in pend if not S.owner_records(r)]
        if odd:
            other.append('turn %s: %s; %s' % (m.group(1), m.group(2), odd[0][:140]))
        elif pend:
            own += 1
        pend = []
print('observer heartbeat mismatches: %d%s' % (len(hb), '' if not hb else
      ' (after the failed injection above)' if fails else
      ' (NOT injected: the observer pauses from every injection until the healed turn)'))
for l in hb:
    print('  ' + l[:200])
print('observer turns with diffs only in the production records +0x80..+0xa7: %d (owner/non-owner forms between turns, '
      'expected); with other diffs: %d (first 3 lines per instance are logged)' % (own, len(other)))
for l in other:
    print('  ' + l)
for x in 'ABCDE':
    w = [float(m.group(1)) for l in lines(os.path.join(AG, 'player_%s.log' % x))
         for m in [re.search(r'waited ([\d.]+)s for a resync transfer', l)] if m]
    print('agent %s held its input back during %d transfers, %.0fs' % (x, len(w), sum(w)))
EOF
