"""Long natural game: light screen browsing on both instances every turn (as players do), continuous
kill-request tracing, after every turn compare state, RNG/CRCs and order lists. Stops at a heartbeat
mismatch (RNG/CRC differ) or after <turns>.
usage: longrun.py <turns> <seed> <logdir> [--active] [--realistic] [--heavy A|B]"""
import os, random, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
import ordercmp
from autoturn import (u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, snapshot, compare, force_active, Dialogs,
                      handle_dialogs, generic_dismiss)
HERE = os.path.dirname(os.path.abspath(__file__))
n, seed, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
ACTIVE = '--active' in sys.argv
os.makedirs(out, exist_ok=True)
rnd = random.Random(seed); st = H.load_state(); P = {'A': st['A'], 'B': st['B']}; dlg = Dialogs()
LOG = open(os.path.join(out, 'longrun.log'), 'a')
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n'); LOG.flush(); sys.stdout.flush()
def key(inst, vk):
    hw = H.main_window(P[inst]); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)
TABS = [(320, 437), (430, 449), (528, 437), (605, 449), (697, 437)]
HEAVY = sys.argv[sys.argv.index('--heavy') + 1] if '--heavy' in sys.argv else ''
def browse(inst):
    # --heavy A: player A checks the galaxy-map tabs (events, military, ...) several times per turn,
    # as many players do; the other player browses lightly.
    acts = []
    for _ in range(rnd.randint(6, 12) if inst == HEAVY else rnd.randint(1, 4)):
        r = rnd.random()
        if r < 0.55:
            x, y = rnd.choice(TABS); H.click(H.main_window(P[inst]), x, y, pid=P[inst]); acts.append('tab%d' % x)
        elif r < 0.8:
            vk = rnd.choice([0x71, 0x72, 0x73]); key(inst, vk); time.sleep(0.4); key(inst, 0x70); acts.append('F%d' % (vk - 0x6f))
        else:
            key(inst, 0x70); acts.append('F1')
        time.sleep(rnd.uniform(0.1, 0.4))
    return acts
LAYOUT = {
    'A': dict(home=(540, 258), tfx=120, tfy=(300, 345, 385), orders=(100, 568),
              missions=[(285, 258), (285, 330), (285, 372), (430, 330), (430, 372), (285, 397)],
              tabs={'build': (94, 150), 'ships': (94, 178), 'prod': (94, 94)}, buy=(640, 198),
              arrows=((370, 568), (100, 170, 238, 308, 376)), auto=(640, 240), systems=(320, 20)),
    'B': dict(home=(465, 255), tfx=140, tfy=(305, 345, 385), orders=(110, 563),
              missions=[(545, 268), (550, 294), (390, 369), (370, 394), (340, 419), (330, 444), (310, 519)],
              tabs={'build': (90, 143), 'ships': (90, 171), 'prod': (90, 87)}, buy=(650, 207),
              arrows=((375, 582), (104, 175, 246, 317, 388)), auto=(668, 255), systems=(310, 22)),
}
REALISTIC = '--realistic' in sys.argv
def credits(inst):
    p = P[inst]; emp = H.readmem(p, 0x5a2b2a, 1)[0]
    return struct.unpack('<i', H.readmem(p, 0x5b1b30 + emp * 0x1bc, 4))[0]
def hold(inst, xy, t=0.5):
    # labor arrows react only to a held button
    p = P[inst]; hw = H.main_window(p)
    H.set_cursor(p, *xy); time.sleep(0.15); cx, cy = H.game2client(hw, *xy)
    H.user32.PostMessageW(hw, H.WM_MOUSEMOVE, 0, H.lparam(cx, cy)); time.sleep(0.05)
    H.user32.PostMessageW(hw, H.WM_LBUTTONDOWN, H.MK_LBUTTON, H.lparam(cx, cy)); time.sleep(t)
    H.user32.PostMessageW(hw, H.WM_LBUTTONUP, 0, H.lparam(cx, cy)); time.sleep(0.4)
def economy(inst):
    """What players do in long games besides fleets: move labor, switch auto/manual build,
    queue (multi-turn) builds in colonies, sometimes buy."""
    L = LAYOUT[inst]; acts = []
    key(inst, 0x70); time.sleep(0.4); click(inst, L['home'], 0.5); key(inst, 0x71); time.sleep(0.8)
    if rnd.random() < 0.5:                                     # labor at the home system
        click(inst, L['tabs']['prod'], 0.6)
        for _ in range(rnd.randint(1, 3)):
            side = rnd.randint(0, 1); row = rnd.randint(0, 4)
            hold(inst, (L['arrows'][0][side], L['arrows'][1][row]), rnd.uniform(0.2, 0.8)); acts.append('labor%d%s' % (row, '-+'[side]))
    if rnd.random() < 0.08:
        click(inst, L['auto'], 0.6); acts.append('autotoggle')
    if rnd.random() < 0.6:                                     # a colony
        click(inst, L['systems'], 0.9); k = rnd.randint(0, 3); click(inst, (300, 111 + 18 * k), 0.9)
        click(inst, L['tabs']['build'], 0.6); click(inst, (300, 113 + 16 * rnd.randint(0, 9)), 0.5); acts.append('colony%d' % k)
        if rnd.random() < 0.25 and credits(inst) > 3000:
            click(inst, L['buy'], 0.5); acts.append('colonybuy')
        if rnd.random() < 0.3:
            click(inst, L['tabs']['prod'], 0.6)
            hold(inst, (L['arrows'][0][rnd.randint(0, 1)], L['arrows'][1][rnd.randint(0, 4)]), 0.5); acts.append('colonylabor')
    esc_safe(inst); key(inst, 0x70); time.sleep(0.4)
    return acts
MENU_IMG = None
def menu_open(inst):
    global MENU_IMG
    from PIL import Image, ImageChops, ImageStat
    from autoturn import screen, TPL
    if MENU_IMG is None:
        MENU_IMG = Image.open(os.path.join(TPL, 'mainmenu_continue.png')).convert('RGB')
    img = screen(inst, P[inst], 'lr_menu').convert('RGB')
    return sum(ImageStat.Stat(ImageChops.difference(img.crop((655, 105, 780, 140)), MENU_IMG)).mean) / 3 < 25
def esc_safe(inst):
    key(inst, 0x1b); time.sleep(0.6)
    if menu_open(inst):
        H.click(H.main_window(P[inst]), 705, 122, pid=P[inst]); time.sleep(1.5)
def click(inst, xy, wait=0.35):
    H.click(H.main_window(P[inst]), xy[0], xy[1], pid=P[inst]); time.sleep(wait)
def play(inst):
    L = LAYOUT[inst]; acts = []
    key(inst, 0x70); time.sleep(0.5)
    for _ in range(rnd.randint(1, 3)):                       # fleets at the home system
        click(inst, L['home'], 0.6)
        click(inst, (L['tfx'], rnd.choice(L['tfy'])), 0.5)
        r = rnd.random()
        if r < (0.2 if REALISTIC else 0.55):                   # realistic: most fleets stay home and defend
            dst = (rnd.randint(275, 745), rnd.randint(50, 400)); click(inst, dst, 0.5); acts.append('move%d,%d' % dst)
        elif r < (0.5 if REALISTIC else 0.85):
            click(inst, L['orders'], 0.9); m = rnd.choice(L['missions']); click(inst, m, 0.6); acts.append('mission%d,%d' % m)
            esc_safe(inst); key(inst, 0x70); time.sleep(0.4)
    if rnd.random() < 0.6:                                     # production at the home system
        click(inst, L['home'], 0.5); key(inst, 0x71); time.sleep(0.8)
        click(inst, L['tabs']['build'], 0.6); click(inst, (300, 113 + 16 * rnd.randint(0, 3)), 0.5); acts.append('build')
        if rnd.random() < 0.4:
            click(inst, L['tabs']['ships'], 0.6); click(inst, (300, 113 + 16 * rnd.randint(0, 2)), 0.5); acts.append('ship')
        if rnd.random() < (0.7 if credits(inst) > 100000 else 0.3) and credits(inst) > 3000:   # no buying into debt
            click(inst, L['buy'], 0.5); acts.append('buy')
        key(inst, 0x70); time.sleep(0.5)
    return acts

def pressed(inst, t):
    return i32(P[inst], BUSY_ADDR) != 0 or u32(P[inst], TURN_ADDR) > t
def press(inst, t):
    for attempt in range(8):
        if pressed(inst, t): return True
        if not handle_dialogs(dlg, inst, P[inst], log) and attempt >= 2:
            generic_dismiss(inst, P[inst], log)
        if pressed(inst, t): return True
        H.click(H.main_window(P[inst]), *TURN_BTN[inst], pid=P[inst])
        for _ in range(10):
            time.sleep(0.3)
            if pressed(inst, t): return True
        time.sleep(1.0)
    return False

stopf = os.path.join(out, 'ktrace.stop')
if os.path.exists(stopf): os.remove(stopf)
env = dict(os.environ, TRACER_STOP=stopf, ONLY2='1')
tr = [subprocess.Popen([sys.executable, '-I', '-u', os.path.join(HERE, 'ktrace.py'), str(P[x]), '86400'],
                       stdout=open(os.path.join(out, 'ktrace_%s.log' % x), 'a'), stderr=subprocess.STDOUT, env=env) for x in 'AB']
time.sleep(3)
MASK0 = H.readmem(P['A'], 0x5a2b28, 1)[0]
try:
    for k in range(n):
        force_active(P)
        t = u32(P['A'], TURN_ADDR)
        acts = ['A:' + a for a in browse('A')] + ['B:' + a for a in browse('B')]
        if ACTIVE:
            acts += ['A:' + a for a in play('A')] + ['B:' + a for a in play('B')]
        if REALISTIC:
            acts += ['A:' + a for a in economy('A')] + ['B:' + a for a in economy('B')]
        if not press('B', t): log('STOP: B press failed at turn', t); break
        if REALISTIC:                                          # clicking around while waiting for the other player
            acts += ['B(after TURN):' + a for a in browse('B')]
        if not press('A', t): log('STOP: A press failed at turn', t); break
        if REALISTIC and rnd.random() < 0.5:                   # and while the turn is processed
            acts += ['A(processing):' + a for a in browse('A')] + ['B(processing):' + a for a in browse('B')]
        t0 = time.time(); last = t0; result = None
        while True:
            if not (H.pid_alive(P['A']) and H.pid_alive(P['B'])): result = 'dead'; break
            force_active(P)
            if u32(P['A'], TURN_ADDR) > t and u32(P['B'], TURN_ADDR) > t and i32(P['A'], BUSY_ADDR) == 0 and i32(P['B'], BUSY_ADDR) == 0:
                result = 'ok'; break
            if time.time() - t0 > 4 and handle_dialogs(dlg, 'A', P['A'], log) + handle_dialogs(dlg, 'B', P['B'], log):
                last = time.time()
            if time.time() - last > 60 and not getattr(sys, '_tried', 0):
                sys._tried = 1
                from autoturn import screen
                screen('A', P['A'], os.path.join('..', out, 'unknownA_t%d' % t)); screen('B', P['B'], os.path.join('..', out, 'unknownB_t%d' % t))
                generic_dismiss('A', P['A'], log); generic_dismiss('B', P['B'], log); last = time.time()
            if time.time() - last > 120: result = 'stuck'; break
            time.sleep(1.0)
        sys._tried = 0
        if result != 'ok':
            log('turn %d: %s (busy A %d B %d, turn A %d B %d)' % (t, result, i32(P['A'], BUSY_ADDR), i32(P['B'], BUSY_ADDR), u32(P['A'], TURN_ADDR), u32(P['B'], TURN_ADDR)))
            if result == 'stuck':
                from autoturn import screen
                screen('A', P['A'], os.path.join('..', out, 'stuckA_t%d' % t)); screen('B', P['B'], os.path.join('..', out, 'stuckB_t%d' % t))
                for x in 'AB':
                    r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'sampler.py'), x, '3', '50'], capture_output=True, text=True).stdout
                    log('  stack sample %s:' % x); log(r)
            break
        time.sleep(1.0)
        rep = compare(snapshot(P['A']), snapshot(P['B']))
        od, na, nb = ordercmp.compare(P['A'], P['B'])
        hb = [x for x in rep if x.startswith(('RNG differs', 'CRC vars differ', 'turn differs'))]
        masks = [H.readmem(P[x], 0x5a2b28, 1)[0] for x in 'AB']
        log('turn %d -> %d | state diffs %d | order diffs %d | orders %d | %s' % (t, t + 1, len(rep), len(od), na, ' '.join(acts)))
        for x in (rep + od)[:10]: log('    ' + x)
        if hb:
            log('HB MISMATCH at turn %d' % (t + 1)); break
        if masks[0] != masks[1] or masks[0] != MASK0:
            log('PLAYER ELIMINATED or mask changed at turn %d: masks A %#x B %#x' % (t + 1, masks[0], masks[1])); break
finally:
    open(stopf, 'w').close(); time.sleep(5)
    for p in tr:
        try: p.wait(10)
        except Exception: pass
