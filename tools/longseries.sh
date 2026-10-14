#!/bin/bash
# usage: longseries.sh <exe> <runs> <turns> <seed0>
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
EXE=$1; RUNS=$2; N=$3; S0=$4
for r in $(seq 1 $RUNS); do
  SEED=$((S0 + r)); OUT=turnlog/long_${EXE%.exe}_$SEED
  for g in 1 2 3; do
    timeout 400 bash tools/newgame.sh $EXE > /dev/null 2>&1
    python -I tools/rxstat.py 2>/dev/null | grep -q "^B turn 0 busy 0 rxlist [0-9]" && break
    grep -qE "stuck|dead|HB MISMATCH|STOP" $OUT/longrun.log && { echo "run $r ended abnormally, series stopped for inspection"; break; }
done
  echo "=== long $EXE run $r seed $SEED $(date +%H:%M)"
  timeout 30000 python -I -u tools/longrun.py $N $SEED $OUT > /dev/null 2>&1
  echo "run $r: $(grep -c '^turn' $OUT/longrun.log) turns; last: $(tail -1 $OUT/longrun.log | cut -c1-80); $(grep -E 'HB MISMATCH|STOP' $OUT/longrun.log | head -1)"
  echo "   remote kill executions A/B: $(grep -c 'KILL mode 2' $OUT/ktrace_A.log)/$(grep -c 'KILL mode 2' $OUT/ktrace_B.log), matched: $(grep -c 'matched order' $OUT/ktrace_A.log)/$(grep -c 'matched order' $OUT/ktrace_B.log)"
  grep -qE "stuck|dead|HB MISMATCH|STOP" $OUT/longrun.log && { echo "run $r ended abnormally, series stopped for inspection"; break; }
done
