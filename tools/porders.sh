#!/bin/bash
# Partial delivery of a leaver's orders (open point "a player drops out while he sends his orders"): 5 humans from
# <save>; A, C and D end the turn, then E ends it (its orders reach everybody). On B the received-orders slot of E is
# cleared (table 0x5b4870: 4 x {buffer, empire}), as if E's orders never reached B. E's game is killed. B learns of
# the leave while idle and without E's orders and applies it at once (AI takeover); A, C and D wait for B, hold E's
# orders and only mark E gone (Fix LV). Then B ends the turn. Afterwards three turns are played with tools/turn5.py.
# A heartbeat mismatch here means the open point is real.
# usage: porders.sh <exe> [<save>]
cd "$(dirname "$0")/.." || exit 1                 # repository root
SAV=${2:-saves/five_1201_t103}
bash tools/resume5.sh $SAV $1 | tail -1
sleep 3
python -I - <<'PY'
import struct, sys, time, subprocess; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, u32, BUSY_ADDR, TURN_ADDR
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
CLOSE = {'A': [(400, 386)], 'B': [(305, 266)], 'C': [(236, 344)], 'D': [(300, 336), (232, 252)]}
st = H.load_state()
def press(x):
    hw = H.main_window(st[x]); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.5); H.click(hw, *TURN[x], pid=st[x]); time.sleep(0.3)
def slots(x):
    raw = H.readmem(st[x], 0x5b4870, 0x20)
    return [struct.unpack_from('<IB', raw, 8 * i) for i in range(4)]
m0 = H.readmem(st['A'], 0x5a2b28, 1)[0]
emp_e = H.readmem(st['E'], 0x5a2b2a, 1)[0]
t1 = u32(st['A'], TURN_ADDR)
for x in 'ACD':
    press(x)
time.sleep(3)
press('E'); time.sleep(5)
print('E (empire %d) ended' % emp_e, {x: i32(st[x], BUSY_ADDR) for x in 'ABCDE'})
print('slots before', {x: slots(x) for x in 'ABCD'})
for i, (buf, emp) in enumerate(slots('B')):
    if buf and emp == emp_e:
        H.writemem(st['B'], 0x5b4870 + 8 * i, b'\0\0\0\0')
        print('B: cleared slot %d (buffer %#x)' % (i, buf))
subprocess.run(['taskkill', '/PID', str(st['E']), '/F'], capture_output=True)
t0 = time.time()
while time.time() - t0 < 120 and H.readmem(st['B'], 0x5a2b28, 1)[0] == m0:
    time.sleep(1)
print('B saw the drop after %ds' % (time.time() - t0), {x: hex(H.readmem(st[x], 0x5a2b28, 1)[0]) for x in 'ABCD'},
      'gone', {x: H.readmem(st[x], 0x5a1608, 1).hex() for x in 'ABCD'})
time.sleep(2)
for xy in CLOSE['B']:
    H.click(H.main_window(st['B']), *xy, pid=st['B'])
time.sleep(1)
press('B')
t0 = time.time()
while time.time() - t0 < 240 and not all(u32(st[x], TURN_ADDR) > t1 and i32(st[x], BUSY_ADDR) == 0 for x in 'ABCD'):
    for x in 'ACD':
        if i32(st[x], BUSY_ADDR) != 1:
            for xy in CLOSE[x]:
                H.click(H.main_window(st[x]), *xy, pid=st[x])
    time.sleep(5)
print('RESULT', 'advanced' if all(u32(st[x], TURN_ADDR) > t1 for x in 'ABCD') else 'HANG',
      {x: (H.pid_alive(st[x]) and (u32(st[x], TURN_ADDR), i32(st[x], BUSY_ADDR), hex(H.readmem(st[x], 0x5a2b28, 1)[0]))) for x in 'ABCD'})
PY
for i in 1 2 3; do timeout 300 python -I tools/turn5.py 2>&1 | grep "^turn\|MISMATCH\|Error\|error" | head -3 | cut -c1-160; done
