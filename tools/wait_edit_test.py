"""Edit-after-TURN test: B ends the turn, then changes a build queue while waiting; A ends last.
usage: wait_edit_test.py [turns_after]
"""
import os, struct, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, snapshot, compare

st = H.load_state()
P = {'A': st['A'], 'B': st['B']}


def press(name, t):
    pid = P[name]
    for _ in range(4):
        if i32(pid, BUSY_ADDR) != 0 or u32(pid, TURN_ADDR) > t:
            return True
        H.click(H.main_window(pid), *TURN_BTN[name], pid=pid)
        for _ in range(10):
            time.sleep(0.3)
            if i32(pid, BUSY_ADDR) != 0 or u32(pid, TURN_ADDR) > t:
                return True
    return False


def find(name, sysname):
    pid = P[name]
    sp = u32(pid, 0x5a36c8)
    cnt = struct.unpack('<H', H.readmem(pid, 0x5a36bc, 2))[0]
    for i in range(cnt):
        if H.readmem(pid, sp + i * 0x328 + 8, 40).split(b'\0')[0] == sysname:
            return i


def cur(name, idx):
    pid = P[name]
    s = H.readmem(pid, u32(pid, 0x5a36c8) + idx * 0x328, 0x328)
    order, inv, unrest, build = struct.unpack_from('<ihhh', s, 0x80)
    return 'order=%d inv=%d build=%d' % (order, inv, build)


idx = find('B', b"Qo'nos")
t = u32(P['A'], TURN_ADDR)
print('turn', t, "Qo'nos idx", idx, '| A', cur('A', idx), '| B', cur('B', idx))
assert press('B', t)
print('B ended turn (busy=%d); B now edits its queue while waiting' % i32(P['B'], BUSY_ADDR))
subprocess.check_call([sys.executable, '-I', os.path.join(os.path.dirname(__file__), 'queue.py'), 'B', 'fusion', str(idx)])
time.sleep(1)
assert press('A', t)
t0 = time.time()
while not all(u32(P[n], TURN_ADDR) > t and i32(P[n], BUSY_ADDR) == 0 for n in 'AB'):
    time.sleep(0.3)
    if time.time() - t0 > 120:
        raise SystemExit('timeout')
time.sleep(1)
print("after turn: A", cur('A', idx), '| B', cur('B', idx))
rep = compare(snapshot(P['A']), snapshot(P['B']))
print('diffs', len(rep))
for x in rep[:10]:
    print('   ', x)
