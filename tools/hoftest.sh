#!/bin/bash
# Hall of Fame after END TURN (report from the community): from saves/five_1201_t103 B ends the turn, opens the main
# menu (Escape) and the HALL OF FAME and stays there; the others end the turn. Then two more plain turns.
# usage: hoftest.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1 | cut -c1-40
sleep 3
python -I - <<'PY'
import sys, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, force_active
st = H.load_state(); P = {x: st[x] for x in 'ABCDE'}; force_active(P)
hw = H.main_window(P['B']); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.5)
H.click(hw, 110, 22, pid=P['B'])
for _ in range(20):
    time.sleep(0.3)
    if i32(P['B'], 0x5a291c) != 0:
        break
H.user32.PostMessageW(hw, 0x100, 0x1b, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x1b, 0xC0000001); time.sleep(2)
H.click(hw, 705, 410, pid=P['B']); time.sleep(2.5)
print('B in the Hall of Fame, busy', i32(P['B'], 0x5a291c))
PY
for i in 1 2 3; do timeout 300 python -I tools/turn5.py | grep -E "^turn|MISMATCH|timeout" | cut -c1-110; done
for x in A B C D E; do [ -s ../test/$x/Crash.log ] && { echo "Crash.log $x:"; sed -n 4,6p ../test/$x/Crash.log; }; done
