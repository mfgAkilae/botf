"""Race test with real UI: while B (slow) is still calculating turn N, A (already in N+1) adds a
Fusion Plant to Cardassia's build queue via the system screen and ends turn N+1 immediately.
usage: race_ui_test.py <cardassia_x> <cardassia_y>
"""
import os, struct, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, snapshot, compare
from race_test import press, cardassia, cur, P

cx, cy = int(sys.argv[1]), int(sys.argv[2])
here = os.path.dirname(os.path.abspath(__file__))


def dbl(inst, x, y):
    subprocess.check_call([sys.executable, '-I', os.path.join(here, 'dblclick.py'), inst, str(x), str(y)])


idx = cardassia()
t = u32(P['A'], TURN_ADDR)
print('turn', t, 'Cardassia', idx, '| A', cur('A', idx), '| B', cur('B', idx))
assert press('B', t) and press('A', t)
t0 = time.time()
while not (u32(P['A'], TURN_ADDR) > t and i32(P['A'], BUSY_ADDR) == 0):
    time.sleep(0.2)
print('A done at %.1fs, B busy=%d' % (time.time() - t0, i32(P['B'], BUSY_ADDR)))
dbl('A', cx, cy); time.sleep(3)
dbl('A', 300, 127); time.sleep(2)
print('A after UI edit:', cur('A', idx))
hw = H.main_window(P['A'])
H.user32.PostMessageW(hw, 0x100, 0x1b, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x1b, 0xC0000001)
time.sleep(1.5); H.click(hw, 705, 122, pid=P['A']); time.sleep(2)
assert press('A', t + 1)
print('A ended turn %d at %.1fs, B busy=%d' % (t + 1, time.time() - t0, i32(P['B'], BUSY_ADDR)))
while not (u32(P['B'], TURN_ADDR) > t and i32(P['B'], BUSY_ADDR) == 0):
    time.sleep(0.3)
time.sleep(1)
print('B done at %.1fs' % (time.time() - t0))
print('A', cur('A', idx), '| B', cur('B', idx))
rep = compare(snapshot(P['A']), snapshot(P['B']))
print('diffs', len(rep)); [print('   ', x) for x in rep[:6]]
