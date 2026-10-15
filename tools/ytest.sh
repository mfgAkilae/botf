#!/bin/bash
# Fix Y / barrier check: 5 humans from saves/five_1201_t103; only E ends the turn (its orders fill a receive slot),
# then E's game is killed. After the drop is detected, A..D end the turn. Original: the stale slot of E (or E's bit
# in the barrier mask) can block the barrier; fixed: A..D process the turn and stay in sync for 3 more turns.
# usage: ytest.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1
sleep 3
python -I - <<'PY'
import sys, time, subprocess; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, u32, BUSY_ADDR, TURN_ADDR
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state()
def press(x):
    hw = H.main_window(st[x]); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.5); H.click(hw, *TURN[x], pid=st[x]); time.sleep(0.3)
m0 = H.readmem(st['A'], 0x5a2b28, 1)[0]
press('E'); time.sleep(5)
print('E ended', {x: i32(st[x], BUSY_ADDR) for x in 'ABCDE'})
subprocess.run(['taskkill', '/PID', str(st['E']), '/F'], capture_output=True)
t0 = time.time()
while time.time() - t0 < 120 and any(H.readmem(st[x], 0x5a2b28, 1)[0] == m0 for x in 'ABCD'):
    time.sleep(1)
print('drop seen after %ds' % (time.time() - t0), {x: hex(H.readmem(st[x], 0x5a2b28, 1)[0]) for x in 'ABCD'})
t1 = u32(st['A'], TURN_ADDR)
for x in 'ABCD':
    press(x)
t0 = time.time()
while time.time() - t0 < 180 and not all(u32(st[x], TURN_ADDR) > t1 and i32(st[x], BUSY_ADDR) == 0 for x in 'ABCD'):
    time.sleep(1)
print('RESULT', 'advanced' if all(u32(st[x], TURN_ADDR) > t1 for x in 'ABCD') else 'HANG',
      {x: (H.pid_alive(st[x]) and (u32(st[x], TURN_ADDR), i32(st[x], BUSY_ADDR))) for x in 'ABCD'})
PY
for i in 1 2 3; do timeout 300 python -I tools/turn5.py 2>&1 | grep "^turn\|MISMATCH\|Error\|error" | head -3 | cut -c1-140; done
