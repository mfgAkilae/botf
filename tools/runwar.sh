#!/bin/bash
# usage: runwar.sh <exe> <logdir> <seed> <turns> <savedir> [manual]   (PLAYER_FLAGS=--assault: war agents)
# Resume a 5-human checkpoint, optionally switch tactical combat to MANUAL on the host (Esc -> OPTIONS ->
# TACTICAL COMBAT OPTIONS -> MANUAL -> ACCEPT -> CONTINUE; the host sends it to everybody), then start the
# observer, the five player agents and tools/tactical.py (plays the manual combats of B and E).
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
EXE=$1; D=$2; SEED=$3; N=$4; SAV=$5; mkdir -p $D
R=$(bash tools/resume5.sh $SAV $EXE | tail -1); echo "$R"; echo "$R" | grep -q "^loaded after" || { echo "resume failed"; exit 1; }
sleep 3
if [ "$6" = manual ]; then
  $H key A 1b; sleep 1.5; $H click A 700 362; sleep 1.5; $H click A 340 354; sleep 1; $H click A 545 422; sleep 1
  $H click A 545 528; sleep 2; $H click A 705 122; sleep 3
  python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; print('combat mode', [H.readmem(H.load_state()[x],0x5a2b68,4).hex() for x in 'ABCDE'])"
fi
nohup python -I -u tools/observer.py $N $D > $D/observer_stdout.txt 2>&1 &
sleep 6
for x in A B C D E; do f=""; [ $x = A ] && f="--heavy"; nohup python -I -u tools/player.py $x $SEED $D $f $PLAYER_FLAGS > $D/player_${x}_stdout.txt 2>&1 & sleep 1; done
[ "$6" = manual ] && nohup python -I -u tools/tactical.py 86400 $D $SEED > $D/tactical_stdout.txt 2>&1 &
echo started $D
