#!/bin/bash
# Repeat the turn-320 replay of run nat5_bug_1402 (where instance C once exited silently during turn 321)
# with exception tracers on all games until a game dies; the tracer log then holds the exception/exit code.
# usage: deathhunt.sh <exe> <tries> <last_turn>
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
EXE=$1; N=$2; LAST=${3:-323}
for i in $(seq 1 $N); do
  D=turnlog/death_$i; mkdir -p $D; rm -f $D/ktrace.stop
  timeout 900 bash tools/resume_n.sh saves/nat5_bug_1402_t320 $EXE B C E > $D/resume.out 2>&1 || { echo "try $i: resume failed"; continue; }
  for x in B C E; do
    PX=$(python -I -c "import sys;sys.path.insert(0,'tools');import harness as H;print(H.load_state()['$x'])")
    TRACER_STOP=$D/ktrace.stop ONLY2=1 nohup python -I -u tools/ktrace.py $PX 3600 > $D/ktrace_$x.log 2>&1 &
  done
  sleep 4
  timeout 1200 python -I -u tools/replay.py turnlog/nat5_bug_1402 320 $LAST > $D/replay.out 2>&1
  sleep 5; : > $D/ktrace.stop; sleep 6
  dead=$(python -I -c "import sys;sys.path.insert(0,'tools');import harness as H;st=H.load_state();print(' '.join(k for k in 'BCE' if not H.pid_alive(st[k])))")
  echo "try $i: dead=[$dead] $(grep -c '^turn' $D/replay.out) turns; $(grep -h 'EXCEPTION\|exited' $D/ktrace_*.log | head -3 | cut -c1-300)"
  if [ -n "$dead" ] || grep -q "EXCEPTION" $D/ktrace_*.log; then echo "CAUGHT in $D"; break; fi
done
