"""Play exactly one turn on all running instances (no other input), then compare every game with the host.
usage: turn5.py [sysidx ...]   prints production record / martial-law word / morale of the given systems after the turn."""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, snapshot, compare, force_active, Dialogs, handle_dialogs

TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state(); NAMES = [k for k in 'ABCDE' if k in st and H.pid_alive(st[k])]; P = {k: st[k] for k in NAMES}
dlg = Dialogs()


def key(x, vk):
    hw = H.main_window(P[x]); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)


def press(x, t):
    for _ in range(8):
        if i32(P[x], BUSY_ADDR) != 0 or u32(P[x], TURN_ADDR) > t:
            return True
        key(x, 0x70); time.sleep(0.5)
        handle_dialogs(dlg, x, P[x], print)
        H.click(H.main_window(P[x]), *TURN[x], pid=P[x])
        for _ in range(10):
            time.sleep(0.3)
            if i32(P[x], BUSY_ADDR) != 0 or u32(P[x], TURN_ADDR) > t:
                return True
    return False


force_active(P)
t = u32(P[NAMES[0]], TURN_ADDR)
for x in NAMES:
    assert press(x, t), 'TURN press failed on ' + x
t0 = time.time()
while not all(u32(P[x], TURN_ADDR) > t and i32(P[x], BUSY_ADDR) == 0 for x in NAMES):
    force_active(P)
    if time.time() - t0 > 5:
        for x in NAMES:
            handle_dialogs(dlg, x, P[x], print)
    if time.time() - t0 > 300:
        print('timeout', {x: (u32(P[x], TURN_ADDR), i32(P[x], BUSY_ADDR)) for x in NAMES}); break
    time.sleep(1)
time.sleep(1.5)
print('turn %d -> %d in %.0fs, crc %s' % (t, u32(P[NAMES[0]], TURN_ADDR), time.time() - t0,
      {x: H.readmem(P[x], 0x597610, 10).hex() for x in NAMES}))
s0 = snapshot(P[NAMES[0]])
for x in NAMES[1:]:
    rep = compare(s0, snapshot(P[x]))
    hb = [r for r in rep if r.startswith(('RNG', 'CRC', 'turn'))]
    print('  %s vs %s: %d diffs%s' % (NAMES[0], x, len(rep), '  HEARTBEAT MISMATCH' if hb else ''))
    for r in rep[:6]:
        print('     ', r[:200])
for a in sys.argv[1:]:
    i = int(a)
    for x in NAMES:
        s = H.readmem(P[x], u32(P[x], 0x5a36c8) + i * 0x328, 0x328)
        print('  sys %d %s rec80 %s +86=%d morale %d mlvl %d flags2e0 %s' % (i, x, s[0x80:0x9a].hex(), struct.unpack_from('<h', s, 0x86)[0],
              struct.unpack_from('<h', s, 0x2dc)[0], struct.unpack_from('<h', s, 0x2de)[0], s[0x2e0:0x2f0].hex()))
