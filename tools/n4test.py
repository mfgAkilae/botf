"""Review finding N4: a player whose game window is inactive (alt-tab) when the last orders of a turn arrive.
The game then stays in the message pump of FUN_00458170 (0x4024c0 calls WaitMessage while [0x5a28d4] == 0) with
busy = -1 and does not start the turn processing, but it still dispatches network messages. The others process
the turn and play the next one; their next-turn queues (0x74) and orders (0x68) reach the waiting game before it
processed the current turn.
Steps: <slow> presses TURN and goes inactive; the others press TURN, process the turn and press TURN again (next
turn); after <wait> seconds <slow> becomes active again. Then everybody plays one more turn; prints the turn,
busy and checksum words of every game after each step.
usage: n4test.py [slow] [wait]"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, ACTIVE_ADDR, Dialogs, handle_dialogs

TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
SLOW = sys.argv[1] if len(sys.argv) > 1 else 'B'
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 10
st = H.load_state(); P = {k: st[k] for k in 'ABCDE'}
FAST = [x for x in 'ABCDE' if x != SLOW]
dlg = Dialogs()


def active(names, on=True):
    for x in names:
        if i32(P[x], ACTIVE_ADDR) != int(on):
            H.writemem(P[x], ACTIVE_ADDR, struct.pack('<i', int(on)))
            H.user32.PostMessageW(H.main_window(P[x]), 0, 0, 0)


def state(tag):
    print('%-28s' % tag, ' '.join('%s:t%d/b%d/%s' % (x, u32(P[x], TURN_ADDR), i32(P[x], BUSY_ADDR),
                                                       H.readmem(P[x], 0x597610, 10).hex()) for x in 'ABCDE'))
    sys.stdout.flush()


def press(x):
    t = u32(P[x], TURN_ADDR)
    for _ in range(8):
        H.user32.PostMessageW(H.main_window(P[x]), 0x100, 0x70, 1); time.sleep(0.5)
        H.click(H.main_window(P[x]), *TURN[x], pid=P[x])
        for _ in range(10):
            time.sleep(0.3)
            if i32(P[x], BUSY_ADDR) != 0 or u32(P[x], TURN_ADDR) > t:
                return True
    return False


def wait_until(cond, names, limit=180):
    t0 = time.time()
    while not cond():
        active(names)
        if time.time() - t0 > 5:
            for x in names:
                handle_dialogs(dlg, x, P[x], print)
        if time.time() - t0 > limit:
            return False
        time.sleep(0.5)
    return True


active('ABCDE')
t = u32(P['A'], TURN_ADDR)
state('start')
assert press(SLOW)
active([SLOW], False)
state('%s ended, inactive' % SLOW)
for x in FAST:
    assert press(x), x
ok = wait_until(lambda: all(u32(P[x], TURN_ADDR) > t and i32(P[x], BUSY_ADDR) == 0 for x in FAST), FAST)
state('others processed' if ok else 'others NOT processed')
if ok:
    for x in FAST:
        press(x)
    time.sleep(WAIT)
    state('others ended next turn')
active([SLOW])
wait_until(lambda: u32(P[SLOW], TURN_ADDR) > t and i32(P[SLOW], BUSY_ADDR) == 0, 'ABCDE', 120)
time.sleep(2)
state('%s active again' % SLOW)
if ok:
    press(SLOW)
    wait_until(lambda: all(u32(P[x], TURN_ADDR) > t + 1 and i32(P[x], BUSY_ADDR) == 0 for x in 'ABCDE'), 'ABCDE', 180)
    time.sleep(2)
    state('next turn')
