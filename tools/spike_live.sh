#!/bin/bash
# usage: spike_live.sh <logdir> <seed> <turns> <transfer_turn> ...
# Resync spike under play: observer, five player agents and tactical.py on the running game; at each
# <transfer_turn> the agents pause (<logdir>/pause), tools/spike.py transfers the host's game with a divergence
# poked on a client, the agents resume. The observer compares every turn and stops at a heartbeat mismatch.
cd "$(dirname "$0")/.." || exit 1                 # repository root
D=$1; SEED=$2; N=$3; shift 3; mkdir -p $D; rm -f $D/stop $D/pause
PY=python
nohup python -I -u tools/observer.py $N $D > $D/observer_stdout.txt 2>&1 &
sleep 6
for x in A B C D E; do nohup python -I -u tools/player.py $x $SEED $D > $D/player_${x}_stdout.txt 2>&1 & sleep 1; done
nohup python -I -u tools/tactical.py 86400 $D $SEED > $D/tactical_stdout.txt 2>&1 &
turn() { python -I -c "import sys,struct; sys.path.insert(0,'tools'); import harness as H; print(struct.unpack('<I', H.readmem(H.load_state()['A'], 0x5a2918, 4))[0])"; }
victims=(C D B E)
k=0
for T in "$@"; do
  until [ "$(turn)" -ge "$T" ] || [ -e $D/stop ]; do sleep 5; done
  [ -e $D/stop ] && break
  v=${victims[$((k % 4))]}; k=$((k + 1))
  touch $D/pause; sleep 6
  echo "=== transfer at turn $(turn), divergence on $v $(date +%T)" | tee -a $D/spike.log
  $PY -I tools/spike.py run --diverge $v:$((k + 2)) >> $D/spike.log 2>&1
  turn > $D/resync_turn            # player.py skips the diplomacy screen in this turn (spike finding F)
  grep -E "transfer|FAIL|TIMEOUT" $D/spike.log | tail -3
  rm -f $D/pause
done
until [ -e $D/stop ]; do sleep 10; done
echo "observer stopped: $(grep -E 'STOP|done' $D/observer.log | tail -1)"
