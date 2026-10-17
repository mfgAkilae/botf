"""Review finding S4: task-force reorganisation (REDEPLOY dialog) after the turn timer ended the turn.
Needs a game with a strategic timer (newgame5.sh NEWGAME_TIMER=1) and B's three starting task forces at Qo'nos.
At the start of a turn B selects its first task force (task force panel), opens REDEPLOY and waits; with --idle
the drag happens right away, otherwise after the timer ended B's turn (the last player's expiry is delayed a
little). The drag moves the right-hand ship of the upper row into the task force. Prints the task-force ids
(+0x50) of B's ships in every game before, after the drag and after the turn, and the checksum words.
usage: s4redeploy.py [--idle]"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import i32, u32, force_active

X = 'B'
st = H.load_state(); P = {k: st[k] for k in 'ABCDE'}
emp = H.readmem(P[X], 0x5a2b2a, 1)[0]
LAST = max(P, key=lambda k: H.readmem(P[k], 0x5a2b2a, 1)[0])
IDLE = '--idle' in sys.argv


def ships(pid):
    obj = u32(pid, 0x5b2344); base, size, n = u32(pid, obj + 0x20), u32(pid, obj + 0x10), u32(pid, obj + 0x18)
    raw = H.readmem(pid, base, size * n)
    return [(i, struct.unpack_from('<h', raw, i * size + 0x50)[0]) for i in range(n)
            if struct.unpack_from('<H', raw, i * size + 0x28)[0] == emp]


def mouse(x, y, msg, wp):
    pid = P[X]; hw = H.main_window(pid); H.set_cursor(pid, x, y)
    cx, cy = H.game2client(hw, x, y); H.user32.PostMessageW(hw, msg, wp, H.lparam(cx, cy))


def drag(a, b):
    mouse(a[0], a[1], 0x200, 0); time.sleep(0.2); mouse(a[0], a[1], 0x201, 1); time.sleep(0.3)
    for k in range(1, 11):
        mouse(a[0] + (b[0] - a[0]) * k // 10, a[1] + (b[1] - a[1]) * k // 10, 0x200, 1); time.sleep(0.05)
    time.sleep(0.2); mouse(b[0], b[1], 0x202, 0); time.sleep(1.0)


def show(tag):
    print('%-26s' % tag, {k: ships(P[k]) for k in 'AB'}, 'same everywhere:', len(set(str(ships(P[k])) for k in P)) == 1)


while True:
    force_active(P)
    if all(i32(P[k], 0x5a291c) == 0 for k in P) and i32(P[X], 0x593064) > 5000:
        break
    time.sleep(0.3)
t = u32(P[X], 0x5a2918)
hw = H.main_window(P[X])
H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.6)
mouse(110, 305, 0x200, 0); time.sleep(0.2)                     # double-click the first task force in the panel
mouse(110, 305, 0x201, 1); time.sleep(0.05); mouse(110, 305, 0x202, 0); time.sleep(0.08)
mouse(110, 305, 0x203, 1); time.sleep(0.05); mouse(110, 305, 0x202, 0); time.sleep(1.0)
H.click(hw, 115, 545, pid=P[X]); time.sleep(1.2)                # REDEPLOY
H.capture(hw, 'shots/s4_open.png')
show('turn %d, dialog open' % t)
if not IDLE:
    while i32(P[X], 0x5a291c) == 0:
        force_active(P); time.sleep(0.1)
    if LAST != X:
        H.writemem(P[LAST], 0x593064, struct.pack('<i', i32(P[LAST], 0x593064) + 1500))
    print('%s ended by the timer (busy %d)' % (X, i32(P[X], 0x5a291c)))
drag((610, 75), (330, 500))
H.capture(hw, 'shots/s4_drag.png')
show('after the drag')
if IDLE:
    H.click(hw, 125, 548, pid=P[X]); time.sleep(1.0)            # DONE
while not all(u32(P[k], 0x5a2918) > t and i32(P[k], 0x5a291c) == 0 for k in P):
    force_active(P); time.sleep(0.5)
time.sleep(1)
show('after the turn')
print('crc', {k: H.readmem(P[k], 0x597610, 10).hex() for k in P})
