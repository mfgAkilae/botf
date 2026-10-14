#!/bin/bash
# usage: campaign.sh <exe> <runs> <turns> <seed0> — natural runs from turn 0 with random UI, kill tracing, heartbeat criterion
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
EXE=$1; RUNS=$2; N=$3; S0=$4
for r in $(seq 1 $RUNS); do
  SEED=$((S0 + r)); OUT=turnlog/camp_${EXE%.exe}_$SEED; mkdir -p $OUT; rm -f turnlog/rng_t*.log
  for g in 1 2 3; do
    timeout 400 bash tools/newgame.sh $EXE > /dev/null 2>&1
    python -I tools/rxstat.py 2>/dev/null | grep -q "^B turn 0 busy 0 rxlist [0-9]" && break
  done
  echo "=== campaign $EXE run $r seed $SEED $(date +%H:%M)" | tee -a turnlog/chaos.log
  timeout 14000 python -I -u tools/chaos.py $N $SEED --ktrace --hb > $OUT/chaos.out 2>&1
  touch turnlog/tracer.stop; sleep 6; rm -f turnlog/tracer.stop
  mv turnlog/rng_t*.log $OUT/ 2>/dev/null
  echo "run $r: $(grep -c '^turn' $OUT/chaos.out) turns; $(grep -E 'HB MISMATCH|STOP|BEFORE' $OUT/chaos.out | head -1); $(python -I tools/hits.py $OUT | tail -1)"
done
