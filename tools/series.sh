#!/bin/bash
# usage: series.sh <turns> <seed> exe...   — per exe: new game + chaos (heartbeat criterion), logs in turnlog/series_<exe>.log
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
N=$1; SEED=$2; shift 2
for EXE in "$@"; do
  L=turnlog/series_${EXE%.exe}_$SEED.log
  bash tools/newgame.sh $EXE > /dev/null 2>&1
  python -I tools/rxstat.py > $L 2>&1
  mkdir -p turnlog/k_${EXE%.exe}_$SEED; rm -f turnlog/rng_t*.log
  echo "=== series $EXE seed $SEED $(date +%H:%M)" >> turnlog/chaos.log
  timeout 7200 python -I -u tools/chaos.py $N $SEED --ktrace --hb >> $L 2>&1
  mv turnlog/rng_t*.log turnlog/k_${EXE%.exe}_$SEED/ 2>/dev/null
  echo "=== end $(date +%H:%M)" >> $L
done
