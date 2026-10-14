#!/bin/bash
# Edit-after-TURN via real UI: B ends turn, then double-clicks "Class 2 Hunting Ground" in Qo'nos; A ends last.
# usage: wait_edit_ui_test.sh <exe> <qonos_x> <qonos_y>
cd /e/dev/botf/work
H="python -I tools/harness.py"
EXE=$1; QX=$2; QY=$3
bash tools/newgame.sh "$EXE" >/dev/null 2>&1
timeout 300 python -I -u tools/autoturn.py 1 | tail -1
python -I - <<'EOF'
import sys,time; sys.path.insert(0,'tools'); import harness as H
from autoturn import u32,i32,TURN_ADDR,BUSY_ADDR,TURN_BTN
P=H.load_state(); t=u32(P['B'],TURN_ADDR)
H.click(H.main_window(P['B']),*TURN_BTN['B'],pid=P['B'])
for _ in range(20):
    time.sleep(0.3)
    if i32(P['B'],BUSY_ADDR)!=0: break
print('B busy after TURN:', i32(P['B'],BUSY_ADDR))
EOF
python -I tools/dblclick.py B $QX $QY; sleep 3
$H shot B shots/wu_b1.png >/dev/null
python -I tools/dblclick.py B 300 113; sleep 2
$H shot B shots/wu_b2.png >/dev/null
python -I tools/queue.py B show 3 | head -3
python -I tools/queue.py A show 3 | head -3
