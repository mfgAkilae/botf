"""Review finding R1: research allocations committed after the turn timer ended the turn.
Needs a game with a strategic timer (newgame5.sh NEWGAME_TIMER=1). At the start of a turn <inst> opens the research
screen (F4); when the timer ends its turn (busy -1) the others' expiry is delayed a little (E's countdown), <inst>
changes the allocations ([[0x5cba30]+0x54], six values as the sliders write them) and leaves the screen with the
SUMMARY button. After the turn the research record of <inst>'s empire (0x5b17e8 + emp*0x14 + 6, six words) is
printed for every game.
usage: r1timer.py [inst]"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import i32, u32, force_active

X = sys.argv[1] if len(sys.argv) > 1 else 'B'
st = H.load_state(); P = {k: st[k] for k in 'ABCDE'}
emp = H.readmem(P[X], 0x5a2b2a, 1)[0]
LAST = max(P, key=lambda k: H.readmem(P[k], 0x5a2b2a, 1)[0])     # the timer of the highest empire expires last


def key(x, vk):
    hw = H.main_window(P[x]); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)


def record(x):
    return list(struct.unpack('<6h', H.readmem(P[x], 0x5b17e8 + emp * 0x14 + 6, 12)))


while True:
    force_active(P)
    if all(i32(P[k], 0x5a291c) == 0 for k in P) and i32(P[X], 0x593064) > 5000:
        break
    time.sleep(0.3)
t = u32(P[X], 0x5a2918)
key(X, 0x70); time.sleep(0.5); key(X, 0x73); time.sleep(1.5)
ui = u32(P[X], 0x5cba30)
print('turn', t, 'record', {k: record(k) for k in P})
while i32(P[X], 0x5a291c) == 0:
    force_active(P); time.sleep(0.1)
if LAST != X:
    H.writemem(P[LAST], 0x593064, struct.pack('<i', i32(P[LAST], 0x593064) + 1500))
print('%s ended by the timer (busy %d), screen data %s' % (X, i32(P[X], 0x5a291c),
      [struct.unpack('<i', H.readmem(P[X], ui + 0x3c + 4 * i, 4))[0] for i in range(12)]))
for i, v in enumerate((40, 12, 12, 12, 12, 12)):
    H.writemem(P[X], ui + 0x54 + 4 * i, struct.pack('<i', v))
H.click(H.main_window(P[X]), 100, 20, pid=P[X]); time.sleep(1.0)
print('after leaving the screen, busy %d, record on %s: %s' % (i32(P[X], 0x5a291c), X, record(X)))
while not all(u32(P[k], 0x5a2918) > t and i32(P[k], 0x5a291c) == 0 for k in P):
    force_active(P); time.sleep(0.5)
time.sleep(1)
print('after the turn', {k: record(k) for k in P})
print('crc', {k: H.readmem(P[k], 0x597610, 10).hex() for k in P})
