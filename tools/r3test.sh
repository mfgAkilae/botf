#!/bin/bash
# R3 reproduction (martial-law counter +0x86): from checkpoint saves/five_1201_t103, Cardassian player A
# puts Inquisition (martial law) at the head of Praxis (system 74), plays 2 turns, removes it, re-selects it
# and plays one more turn. Original exe: crcSolarBld differs after that turn ("synchronization error").
# usage: r3test.sh <exe>
set -e
cd /e/dev/botf/work
H="python -I tools/harness.py"
EXE=$1
REC="python -I tools/turn5.py 74"
bash tools/resume5.sh saves/five_1201_t103 $EXE | tail -1
sleep 3
praxis_build() {      # galaxy map -> system screen -> systems list -> Praxis -> build list
  $H key A 70; sleep 0.8; $H key A 71; sleep 1.5
  if [ "$1" = 1 ]; then $H click A 320 20; sleep 1; $H click A 295 116; sleep 1.2; fi   # Praxis from the systems list (once; stays selected)
  $H click A 94 150; sleep 1; $H shot A shots/r3_praxis_$1.png >/dev/null
}
praxis_build 1
$H click A 638 270; sleep 1.2                  # current build (Science Center): delete?
$H click A 318 226; sleep 1.2                  # YES
$H move A 270 172; sleep 0.5; $H click A 270 172; sleep 1.2   # Inquisition
$H key A 70; sleep 0.8
echo "== turn 1 with martial law"; $REC | grep -E "^turn|MISMATCH"
echo "== turn 2 with martial law"; $REC | grep -E "^turn|MISMATCH"
praxis_build 2
$H click A 638 270; sleep 1.2                  # remove Inquisition (no question at 1 turn left)
$H move A 270 172; sleep 0.5; $H click A 270 172; sleep 1.2   # re-select Inquisition
python -I tools/rec.py 74 | cut -c1-90
$H key A 70; sleep 0.8
echo "== turn after re-select"; $REC | grep -E "^turn|MISMATCH|sys 74"
echo "== one more turn"; $REC | grep -E "^turn|MISMATCH|sys 74"
