#!/bin/bash
# usage: newwar.sh <exe> <logdir> <seed> <turns> [manual]   (NEWGAME_CFG="" for the default large ring galaxy)
# New 5-human game on a small spiral galaxy (newgame5.sh with NEWGAME_CFG), optionally tactical combat MANUAL
# (same host clicks as runwar.sh), then the observer, five player agents and tools/tactical.py.
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
EXE=$1; D=$2; SEED=$3; N=$4; mkdir -p $D
NEWGAME_CFG="${NEWGAME_CFG-545,476 545,316}" bash tools/newgame5.sh $EXE 2>&1 | tail -2
sleep 3
if [ "$5" = manual ]; then
  $H key A 1b; sleep 1.5; $H click A 700 362; sleep 1.5; $H click A 340 354; sleep 1; $H click A 545 422; sleep 1
  $H click A 545 528; sleep 2; $H click A 705 122; sleep 3
  python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; print('combat mode', [H.readmem(H.load_state()[x],0x5a2b68,4).hex() for x in 'ABCDE'])"
fi
nohup python -I -u tools/observer.py $N $D > $D/observer_stdout.txt 2>&1 &
sleep 6
for x in ${HUMANS:-A B C D E}; do nohup python -I -u tools/player.py $x $SEED $D $PLAYER_FLAGS > $D/player_${x}_stdout.txt 2>&1 & sleep 1; done
[ "$5" = manual ] && nohup python -I -u tools/tactical.py 86400 $D $SEED > $D/tactical_stdout.txt 2>&1 &
echo started $D
