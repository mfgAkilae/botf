#!/bin/bash
# Player leaving under play: tools/runwar.sh with agents on a checkpoint; after <after> turns the game of <victim> is
# killed at a random moment (seconds into the turn, also inside the turn calculation), its agent stops; a helper
# closes the "... Disconnected" boxes on the others for three minutes. The observer (OBSERVER_LEAVE=1) keeps
# comparing the rest. DROP_WHEN=busy: kill the victim inside the turn calculation (busy 1) instead.
# usage: droplive.sh <exe> <logdir> <seed> <turns> <savedir> <victims> <after>   (victims: one or more of A..E, e.g. BD;
#        several victims are killed a few seconds apart)
cd "$(dirname "$0")/.." || exit 1                 # repository root
EXE=$1; D=$2; SEED=$3; N=$4; SAV=$5; V=$6; AFTER=$7
OBSERVER_LEAVE=1 PLAYER_FLAGS="--assault --waitact" bash tools/runwar.sh $EXE $D $SEED $N $SAV manual > $D.start.txt 2>&1; tail -1 $D.start.txt
python -I - $D $V $AFTER $SEED <<'PY'
import os, random, sys, time, subprocess; sys.path.insert(0, 'tools'); import harness as H
from autoturn import u32, i32
D, V, AFTER, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
rnd = random.Random(seed); st = H.load_state(); P = {x: st[x] for x in 'ABCDE'}
t0 = u32(P['A'], 0x5a2918)
while u32(P['A'], 0x5a2918) < t0 + AFTER:
    time.sleep(2)
if os.environ.get('DROP_WHEN') == 'busy':
    while i32(P[V[0]], 0x5a291c) != 1:
        time.sleep(0.05)
    time.sleep(rnd.uniform(0, 1.5))
else:
    time.sleep(rnd.uniform(0, 40))
for i, v in enumerate(V):
    if i:
        time.sleep(rnd.uniform(0, 5))
    alive = [x for x in P if x not in V[:i]]
    print('kill %s at turn %d busy %s' % (v, u32(P[alive[0]], 0x5a2918), {x: i32(P[x], 0x5a291c) for x in alive}), flush=True)
    open(os.path.join(D, 'stop_' + v), 'w').close()
    subprocess.run(['taskkill', '/PID', str(P[v]), '/F'], capture_output=True)
CLOSE = {'A': [(400, 386)], 'B': [(305, 266)], 'C': [(236, 344)], 'D': [(300, 336), (232, 252)], 'E': [(210, 292)]}
end = time.time() + 180; k = 0
while time.time() < end:
    k += 1
    for x, p in P.items():
        if x not in V and H.pid_alive(p) and k <= 3:          # what the others show after the leave
            H.capture(H.main_window(p), os.path.join(D, 'shot_%s_%d.png' % (x, k)))
    for x, p in P.items():
        if x not in V and H.pid_alive(p) and i32(p, 0x5a291c) != 1:
            for xy in CLOSE[x]:
                H.click(H.main_window(p), *xy, pid=p)
    time.sleep(10)
print('closer done', flush=True)
PY
