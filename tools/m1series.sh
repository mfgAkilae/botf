#!/bin/bash
# usage: m1series.sh <exe> <tries> <turns> [demo options]  — new game per try (verified join), then m1demo2
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
EXE=$1; TRIES=$2; TURNS=$3; shift 3
for i in $(seq 1 $TRIES); do
  for g in 1 2 3; do
    timeout 400 bash tools/newgame.sh $EXE > /dev/null 2>&1
    if python -I tools/rxstat.py 2>/dev/null | grep -q "^B turn 0 busy 0 rxlist [0-9]"; then break; fi
    echo "newgame failed, retry $g"
  done
  echo "=== $EXE try $i $(date +%H:%M)"
  timeout 6000 python -I -u tools/m1demo2.py $TURNS "$@"
  rc=$?; echo "rc=$rc"
  [ $rc -ne 3 ] && break
done
