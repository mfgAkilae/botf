#!/bin/bash
# Player drop check: 5 humans from saves/five_1201_t103; everybody ends the turn and E's game is killed as soon as
# the others are processing (busy 1). Then A..D play 3 more turns and are compared.
# usage: droptest.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1
sleep 3
python -I - <<'PY'
import sys, time, subprocess; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, u32, BUSY_ADDR, TURN_ADDR
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state()
for x in 'EABCD':
    hw = H.main_window(st[x]); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.5); H.click(hw, *TURN[x], pid=st[x]); time.sleep(0.3)
t0 = time.time()
while time.time() - t0 < 30 and not any(i32(st[x], BUSY_ADDR) == 1 for x in 'ABCD'):
    time.sleep(0.02)
print('busy at kill', {x: i32(st[x], BUSY_ADDR) for x in 'ABCDE'})
subprocess.run(['taskkill', '/PID', str(st['E']), '/F'], capture_output=True)
time.sleep(60)
print('after', {x: (H.pid_alive(st[x]) and (u32(st[x], TURN_ADDR), i32(st[x], BUSY_ADDR), hex(H.readmem(st[x], 0x5a2b28, 1)[0]))) for x in 'ABCD'})
PY
for i in 1 2 3; do timeout 300 python -I tools/turn5.py 2>&1 | grep "^turn\|MISMATCH\|Error\|error" | head -3 | cut -c1-140; done
