#!/bin/bash
# usage: runlong5.sh <exe> <logdir> <seed> <turns> [savedir] [players...]
# players: the instances in the save, first = host (default A B C D E with A hosting)
# Restart the 5-human game from a checkpoint (default saves/five_1201_t103) with <exe>, then start the
# observer and one independent player agent per window. Stops on heartbeat mismatch, dead game, lag,
# elimination, stuck, or after <turns>.
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
EXE=$1; D=$2; SEED=$3; N=$4; SAV=${5:-saves/five_1201_t103}; shift 5 2>/dev/null; PLAYERS="${*:-A B C D E}"
mkdir -p $D
if [ "$PLAYERS" = "A B C D E" ]; then R=$(bash tools/resume5.sh $SAV $EXE | tail -1); else R=$(bash tools/resume_n.sh $SAV $EXE $PLAYERS | tail -1); fi
echo "$R"; echo "$R" | grep -q "^loaded after" || { echo "resume failed, not starting the run"; exit 1; }
sleep 3
nohup python -I -u tools/observer.py $N $D > $D/observer_stdout.txt 2>&1 &
sleep 6
declare -A HOME=([A]=542,130 [B]=524,255 [C]=542,261 [D]=542,255 [E]=540,387)
for x in $PLAYERS; do
  f=""; [ $x = A ] && f="--heavy"
  nohup python -I -u tools/player.py $x $SEED $D $f --home ${HOME[$x]} > $D/player_${x}_stdout.txt 2>&1 &
  sleep 1
done
echo started $D
