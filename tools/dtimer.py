"""Diplomacy after the turn timer ended the turn (same class as review findings R1/S4: research and task-force
redeploy). Works on a running five-human game. The strategic timer cannot be switched on in a running game from
the UI, so the host's timer option [0x5b1a48] is set to one minute and the host broadcasts its options (message
0x85, FUN_0050d320 via tools/remotecall.py); every client then starts its timer (0x50d3dd). The host itself has
no timer and ends its turns by hand.
Client <X> (layouts below) opens the diplomacy screen and prepares a proposal (<mode> send: PEACE TREATY to the
race in row <row>; accept: the EVENT tab of an incoming proposal). X's countdown is cut to 3 s, the other clients
get 30 s more, so the timer ends X's turn first (busy -1) while the others still play. Then X presses SEND (or
ACCEPT); the host ends its turn. After that turn and two more the heartbeat CRCs are compared (tools/turn5.py).
usage: dtimer.py <X> send <row> | dtimer.py <X> accept"""
import os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import i32, u32, force_active

X, MODE = sys.argv[1], sys.argv[2]; ROW = int(sys.argv[3]) if len(sys.argv) > 3 else 0
LAYOUT = {   # diplomacy screen: race rows (x, y0, dy), PROPOSE, PEACE TREATY, SEND, EVENT tab, ACCEPT
    'B': dict(races=(110, 473, 16), propose=(110, 371), peace=(395, 18), send=(440, 401), event=(110, 398), accept=None),
    'D': dict(races=(90, 474, 16), propose=(115, 372), peace=(400, 27), send=None, event=(110, 401), accept=(312, 420)),
}[X]
st = H.load_state(); P = {k: st[k] for k in 'ABCDE' if k in st and H.pid_alive(st[k])}
HERE = os.path.dirname(os.path.abspath(__file__))
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}


def key(x, vk):
    hw = H.main_window(P[x]); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)


def click(x, xy, wait=0.6):
    H.click(H.main_window(P[x]), *xy, pid=P[x]); time.sleep(wait)


def shot(name):
    H.capture(H.main_window(P[X]), os.path.join(HERE, '..', 'shots', 'dtimer_%s_%s.png' % (X, name)))


def turn5():
    r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'turn5.py')], capture_output=True, text=True, timeout=600)
    print('\n'.join(l[:200] for l in r.stdout.splitlines() if l.startswith('turn') or 'MISMATCH' in l), flush=True)


if i32(P['B'], 0x593058) == 0:                              # clients have no timer yet: host broadcasts one
    H.writemem(P['A'], 0x5b1a48, struct.pack('<i', 1))
    subprocess.run([sys.executable, '-I', os.path.join(HERE, 'remotecall.py'), 'A', '50d320'], check=True)
    time.sleep(2)
for k in P:
    if k != 'A':
        H.writemem(P[k], 0x593064, struct.pack('<i', 60000))  # ten minutes for the setup
while not all(i32(P[k], 0x5a291c) == 0 for k in P):
    force_active(P); time.sleep(0.3)
t = u32(P['A'], 0x5a2918)
print('turn', t, 'timer', {k: (i32(P[k], 0x593058), i32(P[k], 0x593064)) for k in P}, flush=True)
key(X, 0x70); time.sleep(0.5); key(X, 0x74); time.sleep(1.5)
if MODE == 'send':
    r = LAYOUT['races']; click(X, (r[0], r[1] + r[2] * ROW)); click(X, LAYOUT['propose']); click(X, LAYOUT['peace'], 1.0)
else:
    click(X, LAYOUT['event'], 1.0)
shot('prepared')
for k in P:
    if k != 'A':
        H.writemem(P[k], 0x593064, struct.pack('<i', 300 if k == X else 3000))
while i32(P[X], 0x5a291c) == 0:
    force_active(P); time.sleep(0.1)
print('%s ended by the timer: busy' % X, {k: i32(P[k], 0x5a291c) for k in P}, flush=True)
shot('ended')
click(X, LAYOUT['send'] if MODE == 'send' else LAYOUT['accept'], 1.0)
shot('after')
print('after the click: busy', {k: i32(P[k], 0x5a291c) for k in P}, flush=True)
key('A', 0x70); time.sleep(0.5); click('A', TURN['A'])
t0 = time.time()
while not all(u32(P[k], 0x5a2918) > t and i32(P[k], 0x5a291c) == 0 for k in P) and time.time() - t0 < 300:
    force_active(P); time.sleep(0.5)
print('turn', t, '->', {k: u32(P[k], 0x5a2918) for k in P}, flush=True)
for k in P:
    if k != 'A':
        H.writemem(P[k], 0x593064, struct.pack('<i', 60000))
for _ in range(2):
    turn5()
