"""Drive both instances through N turns, handle known dialogs, diff game state after each turn.
usage: autoturn.py <nturns> [--shots]
Known dialogs are template-matched (tpl/dialogs.json). An unknown blocking state stops the run
and leaves screenshots in turnlog/ for inspection instead of clicking blindly.
"""
import json, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from PIL import Image, ImageChops, ImageStat

TURN_ADDR = 0x5a2918
BUSY_ADDR = 0x5a291c
ACTIVE_ADDR = 0x5a28d4
RNG_ADDR, RNG_LEN = 0x596bac, 0x120
CRC_ADDR = 0x597610
SYS_PTR, SYS_CNT, SYS_SIZE = 0x5a36c8, 0x5a36bc, 0x328
EMP_ADDR, EMP_SIZE, EMP_N = 0x5b1a98, 0x1bc, 5
STN_PTR, STN_CNT, STN_SIZE = 0x5a36d0, 0x5a36c0, 0x5c   # starbases/outposts: in no heartbeat CRC
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(BASE, 'turnlog')
TPL = os.path.join(BASE, 'tpl')
os.makedirs(OUT, exist_ok=True)
TURN_BTN = {'A': (163, 33), 'B': (110, 22)}  # Cardassian / Klingon layouts


def rd(pid, a, n):
    return H.readmem(pid, a, n)


def u32(pid, a):
    return struct.unpack('<I', rd(pid, a, 4))[0]


def i32(pid, a):
    return struct.unpack('<i', rd(pid, a, 4))[0]


def snapshot(pid):
    s = {'turn': u32(pid, TURN_ADDR), 'busy': i32(pid, BUSY_ADDR), 'rng': rd(pid, RNG_ADDR, RNG_LEN), 'crc': rd(pid, CRC_ADDR, 10)}
    sp = u32(pid, SYS_PTR)
    cnt = struct.unpack('<H', rd(pid, SYS_CNT, 2))[0]
    s['nsys'] = cnt
    s['sys'] = rd(pid, sp, cnt * SYS_SIZE) if sp and cnt else b''
    s['emp'] = rd(pid, EMP_ADDR, EMP_SIZE * EMP_N)
    sp = u32(pid, STN_PTR)
    s['nstn'] = struct.unpack('<H', rd(pid, STN_CNT, 2))[0]
    s['stn'] = rd(pid, sp, s['nstn'] * STN_SIZE) if sp and s['nstn'] else b''
    return s


def diff_blocks(a, b, size, label, skip=None):
    out = []
    n = min(len(a), len(b)) // size
    for i in range(n):
        ea, eb = a[i * size:(i + 1) * size], b[i * size:(i + 1) * size]
        if ea == eb:
            continue
        offs = [o for o in range(size) if ea[o] != eb[o] and not (skip and skip(o))]
        if not offs:
            continue
        runs, st, prev = [], offs[0], offs[0]
        for o in offs[1:]:
            if o != prev + 1:
                runs.append((st, prev)); st = o
            prev = o
        runs.append((st, prev))
        out.append('%s[%d]: %s' % (label, i, ', '.join('%#x-%#x a=%s b=%s' % (r0, r1, ea[r0:r1 + 1].hex(), eb[r0:r1 + 1].hex()) for r0, r1 in runs[:12])))
    return out


def sys_skip(o):
    # heap pointers 0xa8..0xbb / 0x30c.., GUI (index 0) copies 0xc0..0x180 and 0x240..0x298
    return 0xa8 <= o < 0xbc or 0xc0 <= o < 0x180 or 0x240 <= o < 0x298 or 0x30c <= o < 0x314


def compare(sa, sb):
    rep = []
    if sa['turn'] != sb['turn']:
        rep.append('turn differs %d vs %d' % (sa['turn'], sb['turn']))
    ra, rb = bytearray(sa['rng']), bytearray(sb['rng'])
    for o in range(4, 0x18):
        ra[o] = rb[o] = 0
    if ra != rb:
        rep.append('RNG differs: seed a=%08x b=%08x' % (struct.unpack_from('<I', sa['rng'])[0], struct.unpack_from('<I', sb['rng'])[0]))
    if sa['crc'] != sb['crc']:
        rep.append('CRC vars differ a=%s b=%s' % (sa['crc'].hex(), sb['crc'].hex()))
    if sa['nsys'] != sb['nsys']:
        rep.append('nsys differs')
    rep += diff_blocks(sa['sys'], sb['sys'], SYS_SIZE, 'sys', skip=sys_skip)
    rep += diff_blocks(sa['emp'], sb['emp'], EMP_SIZE, 'emp', skip=lambda o: 0x50 <= o < 0x98 or 0x154 <= o < 0x158)
    if sa.get('nstn') != sb.get('nstn'):
        rep.append('station count differs %s vs %s' % (sa.get('nstn'), sb.get('nstn')))
    rep += diff_blocks(sa.get('stn', b''), sb.get('stn', b''), STN_SIZE, 'stn')
    return rep


class Dialogs:
    def __init__(self):
        p = os.path.join(TPL, 'dialogs.json')
        self.items = json.load(open(p)) if os.path.exists(p) else []
        for it in self.items:
            it['img'] = Image.open(os.path.join(TPL, it['file'])).convert('RGB')

    def match(self, name, img):
        for it in self.items:
            if it['inst'] != name:
                continue
            crop = img.crop(tuple(it['region'])).convert('RGB')
            d = ImageStat.Stat(ImageChops.difference(crop, it['img'])).mean
            if sum(d) / 3 < it.get('thresh', 25):
                return it
        return None


def screen(name, pid, tag):
    path = os.path.join(OUT, '%s_%s.png' % (tag, name))
    H.capture(H.main_window(pid), path)
    return Image.open(path)


def handle_dialogs(dlg, name, pid, log):
    handled = 0
    for _ in range(6):
        img = screen(name, pid, 'cur')
        it = dlg.match(name, img)
        if not it:
            break
        hw = H.main_window(pid)
        if 'key' in it:
            log('   dialog %s on %s -> key %#x' % (it['name'], name, it['key']))
            H.user32.PostMessageW(hw, H.WM_KEYDOWN, it['key'], 1)
            time.sleep(0.05)
            H.user32.PostMessageW(hw, H.WM_KEYUP, it['key'], 0xC0000001)
        else:
            log('   dialog %s on %s -> click %s' % (it['name'], name, it['click']))
            H.click(hw, *it['click'], pid=pid)
        handled += 1
        time.sleep(2.0)
    return handled


MAINMENU = None


def generic_dismiss(name, pid, log):
    # Unknown dialog: Escape closes most of them; if it opened the in-game main menu instead,
    # leave it via CONTINUE.
    global MAINMENU
    if MAINMENU is None:
        MAINMENU = Image.open(os.path.join(TPL, 'mainmenu_continue.png')).convert('RGB')
    hw = H.main_window(pid)
    H.user32.PostMessageW(hw, H.WM_KEYDOWN, 0x1b, 1)
    time.sleep(0.05)
    H.user32.PostMessageW(hw, H.WM_KEYUP, 0x1b, 0xC0000001)
    time.sleep(1.5)
    img = screen(name, pid, 'cur').convert('RGB')
    d = ImageStat.Stat(ImageChops.difference(img.crop((655, 105, 780, 140)), MAINMENU)).mean
    if sum(d) / 3 < 25:
        H.click(hw, 705, 122, pid=pid)
        time.sleep(2)
        log('   generic dismiss on %s (escape + continue)' % name)
    else:
        log('   generic dismiss on %s (escape)' % name)


def force_active(pids):
    # Test bed: the game counts only the foreground window as active, and an inactive game does
    # not start turn processing (see build_test.py 1c). Two instances cannot both be foreground.
    for pid in pids.values():
        if i32(pid, ACTIVE_ADDR) == 0:
            H.writemem(pid, ACTIVE_ADDR, struct.pack('<i', 1))
            H.user32.PostMessageW(H.main_window(pid), 0, 0, 0)


def main():
    n = int(sys.argv[1])
    shots = '--shots' in sys.argv
    st = H.load_state()
    pids = {'A': st['A'], 'B': st['B']}
    dlg = Dialogs()

    def log(*a):
        print(*a); sys.stdout.flush()

    def pressed(name, t):
        pid = pids[name]
        return i32(pid, BUSY_ADDR) != 0 or u32(pid, TURN_ADDR) > t

    def press(name, t):
        pid = pids[name]
        for attempt in range(8):
            if pressed(name, t):
                return True
            if not handle_dialogs(dlg, name, pid, log) and attempt >= 2:
                screen(name, pid, 'unknown_%d' % attempt)
                generic_dismiss(name, pid, log)
            if pressed(name, t):
                return True
            H.click(H.main_window(pid), *TURN_BTN[name], pid=pid)
            for _ in range(10):
                time.sleep(0.3)
                if pressed(name, t):
                    return True
            time.sleep(1.0)
        screen(name, pid, 'stuck_press')
        log('   STOP: TURN not registered on %s, unknown screen saved to turnlog/stuck_press_%s.png' % (name, name))
        return False

    for i in range(n):
        force_active(pids)
        t = u32(pids['A'], TURN_ADDR)
        if not press('B', t):
            return
        time.sleep(1.0)
        if not press('A', t):
            return
        t0 = time.time()
        last_progress = time.time()
        result = None
        while True:
            if not (H.pid_alive(pids['A']) and H.pid_alive(pids['B'])):
                result = 'dead'; break
            ta, tb = u32(pids['A'], TURN_ADDR), u32(pids['B'], TURN_ADDR)
            ba, bb = i32(pids['A'], BUSY_ADDR), i32(pids['B'], BUSY_ADDR)
            if ta > t and tb > t and ba == 0 and bb == 0:
                result = 'ok'; break
            force_active(pids)
            if time.time() - t0 > 4:
                h = handle_dialogs(dlg, 'A', pids['A'], log) + handle_dialogs(dlg, 'B', pids['B'], log)
                if h:
                    last_progress = time.time()
            if time.time() - last_progress > 90:
                screen('A', pids['A'], 'stuck_wait'); screen('B', pids['B'], 'stuck_wait')
                result = 'stuck (screens in turnlog/stuck_wait_*.png)'; break
            time.sleep(1.5)
        line = 'turn %d -> %d: %s in %.1fs' % (t, t + 1, result, time.time() - t0)
        if result != 'ok':
            log(line); return
        time.sleep(1.5)
        sa, sb = snapshot(pids['A']), snapshot(pids['B'])
        rep = compare(sa, sb)
        log(line, '| diffs:', len(rep))
        for x in rep[:20]:
            log('   ', x)
        with open(os.path.join(OUT, 'turn%03d.json' % (t + 1)), 'w') as f:
            json.dump({'report': rep, 'crc_a': sa['crc'].hex(), 'crc_b': sb['crc'].hex()}, f)
        if shots:
            screen('A', pids['A'], 't%03d' % (t + 1)); screen('B', pids['B'], 't%03d' % (t + 1))


if __name__ == '__main__':
    main()
