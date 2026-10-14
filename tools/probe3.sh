#!/bin/bash
# usage: probe3.sh <label> <nturns> — play turns with the send tracer attached to A (timing perturbation)
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
echo "== $1"
for i in $(seq 1 $2); do
  PID=$(python -I -c "import sys;sys.path.insert(0,'tools');import harness as H;print(H.load_state()['A'])")
  (STACK=6 timeout 200 python -I -u tools/tracer.py $PID 45 519960=send_all 519930=send_930 519990=send_990 5199c0=send_9c0 > turnlog/trace_p3.log 2>&1 &)
  sleep 2
  timeout 400 python -I -u tools/autoturn.py 1 2>&1 | grep -E '^turn|^    |STOP' | head -6
  sleep 44
done
