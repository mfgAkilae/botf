#!/bin/bash
# usage: natural.sh <exe> <turns_without_input> <chaos_turns> <seed>
# natural late-game run: play without input to build a late game, then random UI play with kill tracing
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
EXE=$1; N0=$2; N1=$3; SEED=$4; TAG=${EXE%.exe}_$SEED
OUT=turnlog/nat_$TAG; mkdir -p $OUT; rm -f turnlog/rng_t*.log
for g in 1 2 3; do
  timeout 400 bash tools/newgame.sh $EXE > /dev/null 2>&1
  python -I tools/rxstat.py 2>/dev/null | grep -q "^B turn 0 busy 0 rxlist [0-9]" && break
  echo "newgame failed, retry $g"
done
echo "=== natural $EXE seed $SEED $(date +%H:%M)" | tee -a turnlog/chaos.log
timeout 20000 python -I -u tools/autoturn.py $N0 > $OUT/autoturn.log 2>&1
echo "autoturn done: $(grep -c '^turn' $OUT/autoturn.log) turns, nonzero diffs: $(grep '^turn' $OUT/autoturn.log | grep -vc 'diffs: 0') $(date +%H:%M)"
timeout 20000 python -I -u tools/chaos.py $N1 $SEED --ktrace --hb > $OUT/chaos.out 2>&1
mv turnlog/rng_t*.log $OUT/ 2>/dev/null
echo "chaos done $(date +%H:%M): $(grep -c '^turn' $OUT/chaos.out) turns"
grep -E "HB MISMATCH|STOP|BEFORE" $OUT/chaos.out
