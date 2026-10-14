#!/bin/bash
# usage: runlong5.sh <exe> <logdir> <seed> <turns> [savedir]
# Restart the 5-human game from a checkpoint (default saves/five_1201_t103) with <exe>, then start the
# observer and one independent player agent per window. Stops on heartbeat mismatch, dead game, lag,
# elimination, stuck, or after <turns>.
cd /e/dev/botf/work
EXE=$1; D=$2; SEED=$3; N=$4; SAV=${5:-saves/five_1201_t103}
mkdir -p $D
bash tools/resume5.sh $SAV $EXE | tail -1 || exit 1
sleep 3
nohup python -I -u tools/observer.py $N $D > $D/observer_stdout.txt 2>&1 &
sleep 6
declare -A HOME=([A]=542,130 [B]=524,255 [C]=542,261 [D]=542,255 [E]=540,387)
for x in A B C D E; do
  f=""; [ $x = A ] && f="--heavy"
  nohup python -I -u tools/player.py $x $SEED $D $f --home ${HOME[$x]} > $D/player_${x}_stdout.txt 2>&1 &
  sleep 1
done
echo started $D
