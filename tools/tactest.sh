#!/bin/bash
# Manual tactical combat scenario: from saves/war5_01_t280 the turn-280 processing starts a combat Klingon (B)
# vs Romulan (E) in sector i5. Tactical combat is switched to MANUAL on the host, both pick FIGHT, then the given
# clicks are made in E's tactical view (comma pairs, space separated) and TURN pressed on both, a few rounds.
# usage: tactest.sh <exe> "<clicks for E>" [rounds]
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
EXE=$1; CLICKS=$2; ROUNDS=${3:-3}
bash tools/resume5.sh saves/war5_01_t280 $EXE | tail -1
sleep 3
$H key A 1b; sleep 1.5; $H click A 700 362; sleep 1.5; $H click A 340 354; sleep 1; $H click A 545 422; sleep 1
$H click A 545 528; sleep 2; $H click A 705 122; sleep 3
for x in A B C D E; do : > ${BOTF_TEST:-test}/$x/Crash.log; done
python -I - <<'PY'
import sys, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, BUSY_ADDR
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state()
for x in 'ABCDE':
    hw = H.main_window(st[x]); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.6); H.click(hw, *TURN[x], pid=st[x]); time.sleep(0.6)
time.sleep(20)
print('busy', {x: i32(st[x], BUSY_ADDR) for x in 'ABCDE'})
PY
$H click E 140 272; sleep 0.5; $H click B 278 408; sleep 8              # FIGHT on both
for r in $(seq 1 $ROUNDS); do
  for xy in $CLICKS; do $H click E ${xy%,*} ${xy#*,}; sleep 0.4; done
  $H click E 95 25; sleep 0.5; $H click B 95 25; sleep 12
  python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; st=H.load_state(); print('round $r alive', {x: H.pid_alive(st[x]) for x in 'ABCDE'})"
done
for x in A B C D E; do [ -s ${BOTF_TEST:-test}/$x/Crash.log ] && { echo "Crash.log $x:"; sed -n 4,6p ${BOTF_TEST:-test}/$x/Crash.log; }; done
