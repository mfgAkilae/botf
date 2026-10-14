#!/bin/bash
# Fix M reproduction: from checkpoint saves/five_1201_t103 Cardassian player A deletes the Heavy Cruiser that
# the last turn processing started at Cardassia (system 5, 3244 industry invested, order known only to A),
# then all five play 3 turns. Original: the other machines keep the invested industry, finish the next
# structure a turn early and the heartbeat fails (crcSolarBld) in the 2nd turn.
# usage: mtest.sh <exe> <logdir>
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
H="python -I tools/harness.py"
EXE=$1; D=$2; mkdir -p $D; rm -f $D/ktrace.stop
bash tools/resume5.sh saves/five_1201_t103 $EXE | tail -1
sleep 3
PB=$(python -I -c "import sys;sys.path.insert(0,'tools');import harness as H;print(H.load_state()['B'])")
TRACER_STOP=$D/ktrace.stop ONLY2=1 python -I -u tools/ktrace.py $PB 900 > $D/ktrace_B.log 2>&1 &
sleep 3
$H key A 70; sleep 0.8; $H click A 535 190; sleep 0.8; $H key A 71; sleep 1.5; $H click A 94 150; sleep 1
$H click A 638 270; sleep 1.2                  # Heavy Cruiser at the head: "industry invested. Delete current build?"
$H click A 318 226; sleep 1.2                  # YES
$H key A 70; sleep 0.8
python -I tools/sysdiag.py 5 A B | grep -E "turn|rec80"
for i in 1 2 3; do echo "== turn $i"; python -I tools/turn5.py 5 | grep -E "^turn|MISMATCH|sys 5 [AB]"; done
: > $D/ktrace.stop; sleep 4
grep -B3 -A2 "KILL mode 2" $D/ktrace_B.log | grep -E "payload|seqno|KILL" | head -12
