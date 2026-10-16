#!/bin/bash
# Fix T reproduction: from saves/tac_t293 (war5 game, manual tactical combat on) the Romulan player E sends its
# task force at Beth Delta into Rubicun, where the Edo Guardian (monster) sits. Everybody ends the turn; E gets
# the combat dialog, picks FIGHT and ends the first combat round without giving orders.
# Original: E writes Crash.log "ai\assault.c line 562 entity->ship.shipData.targetIsEntity" and quits.
# usage: tacf.sh <exe>   (POKE=<inst>: that instance gets +0x364 bit 0 set on its monster units)
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
bash tools/resume5.sh saves/tac_t293 $1 | tail -1
sleep 3
for x in A B C D E; do : > ../test/$x/Crash.log; done
$H key E 70; sleep 0.7; $H click E 600 437; sleep 1
$H click E 464 191; sleep 1; $H click E 525 135; sleep 1         # task force Beth Delta -> Rubicun
python -I - <<'PY'
import sys, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, BUSY_ADDR, screen
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state()
screen('E', st['E'], '../shots/edo_course')
for x in 'ABCDE':
    hw = H.main_window(st[x]); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.6); H.click(hw, *TURN[x], pid=st[x]); time.sleep(0.6)
time.sleep(25)
print('busy', {x: i32(st[x], BUSY_ADDR) for x in 'ABCDE'})
screen('E', st['E'], '../shots/edo_dialog')
PY
$H click E 140 272; sleep 8                                       # FIGHT
for x in A B C D E; do python -I tools/monpoke.py $x 0 | head -3; done; [ -n "$POKE" ] && python -I tools/monpoke.py $POKE 1
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; from autoturn import screen; screen('E', H.load_state()['E'], '../shots/edo_tac')"
$H click E 95 25; sleep 1; $H click E 95 25; sleep 20                 # end the combat round without orders
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; st=H.load_state(); print('alive', {x: H.pid_alive(st[x]) for x in 'ABCDE'})"
for x in A B C D E; do [ -s ../test/$x/Crash.log ] && { echo "Crash.log $x:"; sed -n 4,6p ../test/$x/Crash.log; }; done
for i in 1 2; do timeout 300 python -I tools/turn5.py 2>&1 | grep "^turn\|MISMATCH\|Error\|error" | head -3 | cut -c1-140; done
