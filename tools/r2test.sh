#!/bin/bash
# Fix H reproduction (static audit R2, arm B): from checkpoint saves/five_1201_t103 Cardassian player A
# scraps the Union Shipyard at Cardassia (system 5) while it builds a Heavy Cruiser, then all five play
# 5 turns. Original: in the scrap turn only A restarts production from the queue (structure 0x7b) before the
# production snapshot, so A finishes it a turn early -> heartbeat mismatch (crcSolarBld) at turn 106.
# usage: r2test.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1
sleep 3
$H key A 70; sleep 0.8; $H click A 535 190; sleep 0.8; $H key A 71; sleep 1.5
$H click A 94 207; sleep 1.2                                   # STRUCTURES
for i in 1 2 3 4; do $H click A 552 437; sleep 1; done          # page with the Union Shipyard
$H click A 278 355; sleep 1.2                                  # "Scrap Union Shipyard?"
$H click A 318 226; sleep 1.2                                  # YES
$H key A 70; sleep 0.8
for i in 1 2 3 4 5; do echo "== turn $i"; python -I tools/turn5.py 5 | grep -E "^turn|MISMATCH|sys 5 [AB]"; done
