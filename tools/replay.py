"""Replay the recorded inputs of player agents (player_<X>_actions.log) turn by turn on running games.
Each turn: every player's inputs recorded before its TURN press are replayed in order (with the recorded
pauses, capped at 2 s), then TURN, then the inputs it made while waiting; then wait for the next turn and
compare all games (heartbeat CRCs, state).
usage: replay.py <logdir> <first_turn> <last_turn> [sysidx]"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, snapshot, compare, force_active, Dialogs, handle_dialogs

TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
d, t0, t1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
sysidx = int(sys.argv[4]) if len(sys.argv) > 4 else None
st = H.load_state(); NAMES = [k for k in 'ABCDE' if k in st and H.pid_alive(st[k])]; P = {k: st[k] for k in NAMES}
dlg = Dialogs()
REC = {}
for x in NAMES:
    f = os.path.join(d, 'player_%s_actions.log' % x)
    for line in open(f):
        p = line.split(None, 5)
        if len(p) < 6:
            continue
        REC.setdefault((x, int(p[2])), []).append((float(p[0]), int(p[4]), p[5].strip()))


def do(x, a):
    pid = P[x]; hw = H.main_window(pid)
    w = a.split()
    if w[0] == 'key':
        vk = int(w[1], 16); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)
    elif w[0] == 'click':
        xx, yy = map(int, w[1].split(',')); H.click(hw, xx, yy, pid=pid)
    elif w[0] == 'hold':
        xx, yy = map(int, w[1].split(',')); t = float(w[2].rstrip('s'))
        H.set_cursor(pid, xx, yy); time.sleep(0.15); cx, cy = H.game2client(hw, xx, yy)
        H.user32.PostMessageW(hw, H.WM_MOUSEMOVE, 0, H.lparam(cx, cy)); time.sleep(0.05)
        H.user32.PostMessageW(hw, H.WM_LBUTTONDOWN, H.MK_LBUTTON, H.lparam(cx, cy)); time.sleep(t)
        H.user32.PostMessageW(hw, H.WM_LBUTTONUP, 0, H.lparam(cx, cy))
    elif w[0] == 'select':
        ui = struct.unpack('<I', H.readmem(pid, 0x595da8, 4))[0]; H.writemem(pid, ui + 0x1c, struct.pack('<h', int(w[2])))
    elif w[0] == 'TURN':
        H.click(hw, *TURN[x], pid=pid)


def play(x, acts):
    prev = None
    for ts, busy, a in acts:
        if prev is not None:
            time.sleep(min(2.0, max(0.05, ts - prev)))
        prev = ts
        if a.startswith(('esc_safe', 'main menu', 'generic_dismiss')):
            continue
        do(x, a)
    time.sleep(0.5)


for t in range(t0, t1 + 1):
    force_active(P)
    assert all(u32(P[x], TURN_ADDR) == t for x in NAMES), {x: u32(P[x], TURN_ADDR) for x in NAMES}
    for x in NAMES:
        acts = REC.get((x, t), [])
        pre = [a for a in acts if a[1] == 0]
        play(x, pre)
        if not any(a[2] == 'TURN click' for a in pre):
            do(x, 'TURN')
        for _ in range(20):
            if i32(P[x], BUSY_ADDR) != 0 or u32(P[x], TURN_ADDR) > t:
                break
            time.sleep(0.5)
            if _ == 10:
                handle_dialogs(dlg, x, P[x], print); do(x, 'key 0x70'); do(x, 'TURN')
    tw = time.time()
    while not all(u32(P[x], TURN_ADDR) > t and i32(P[x], BUSY_ADDR) == 0 for x in NAMES):
        force_active(P)
        if time.time() - tw > 5:
            for x in NAMES:
                handle_dialogs(dlg, x, P[x], print)
        if time.time() - tw > 300:
            print('timeout'); sys.exit(1)
        time.sleep(1)
    time.sleep(1.5)
    crc = {x: H.readmem(P[x], 0x597610, 10).hex() for x in NAMES}
    s0 = snapshot(P[NAMES[0]]); line = []
    mism = False
    for x in NAMES[1:]:
        rep = compare(s0, snapshot(P[x]))
        hb = [r for r in rep if r.startswith(('RNG', 'CRC', 'turn'))]
        mism |= bool(hb); line.append('%s %d%s' % (x, len(rep), ' HB!' if hb else ''))
    extra = ''
    if sysidx is not None:
        extra = ' | sys%d ' % sysidx + ' '.join('%s:%s' % (x, H.readmem(P[x], u32(P[x], 0x5a36c8) + sysidx * 0x328 + 0x80, 8).hex()) for x in NAMES)
        for x in NAMES:
            pid = P[x]; node = u32(pid, u32(pid, 0x59024c)); o = []
            while node:
                h = H.readmem(pid, node + 8, 0x18); sq, gen, emp = struct.unpack_from('<IIH', h); ty = struct.unpack_from('<i', h, 0x10)[0]
                bp = struct.unpack_from('<I', h, 0x14)[0]
                if ty == 0 and bp:
                    b = H.readmem(pid, bp, 12)
                    if struct.unpack_from('<h', b, 4)[0] == sysidx:
                        o.append('%x/g%d/k%d/%s' % (sq, gen, struct.unpack_from('<I', b, 0)[0], b[8:10].hex()))
                node = u32(pid, node)
            extra += '\n      %s orders: %s' % (x, ' '.join(o) or '-')
    print('turn %d -> %d | %s | crc %s%s' % (t, t + 1, ', '.join(line), crc[NAMES[0]], extra)); sys.stdout.flush()
    if mism:
        print('HEARTBEAT MISMATCH after turn %d' % t); break
