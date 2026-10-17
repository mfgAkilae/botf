"""One independent player agent per game window (run one process per instance, in parallel).
Each agent plays its own empire like a person: browses screens, moves fleets, changes labor and
production, sometimes buys, presses TURN when done and keeps clicking around while it waits for the
other player and while the turn is processed. tools/observer.py traces and compares both games.
usage: player.py <A..E> <seed> <logdir> [--heavy] [--home X,Y]
  --heavy   this player checks the galaxy-map tabs several times per turn
Stops when <logdir>/stop exists; makes no input while <logdir>/pause exists."""
import os, random, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import (u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, ACTIVE_ADDR, Dialogs, handle_dialogs,
                      generic_dismiss, screen, TPL)

INST, seed, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
HEAVY = '--heavy' in sys.argv
ASSAULT = '--assault' in sys.argv            # war in earnest: invasion missions for fleets at foreign systems
os.makedirs(out, exist_ok=True)
rnd = random.Random(seed * 10 + ord(INST))
PID = H.load_state()[INST]
dlg = Dialogs()
STOP = os.path.join(out, 'stop')
PAUSE = os.path.join(out, 'pause')
RESYNC_TURN = os.path.join(out, 'resync_turn')       # tools/spike_live.sh: turn of the last resync transfer
SPEED = float(os.environ.get('BOTF_SPEED', '0.4'))   # scales every pause of the agent (1.0 = slow, human-like)


def nap(t):
    time.sleep(max(0.05, t * SPEED))
    while os.path.exists(PAUSE) and not os.path.exists(STOP):   # resync spike: no input while a transfer runs
        time.sleep(0.2)
LOG = open(os.path.join(out, 'player_%s.log' % INST), 'a')
ACT = open(os.path.join(out, 'player_%s_actions.log' % INST), 'a')


def act(what):
    # every single input, written at once: shows the last thing a player did before a game died
    ACT.write('%.3f turn %d busy %d %s\n' % (time.time(), u32(PID, TURN_ADDR), i32(PID, BUSY_ADDR), what)); ACT.flush()


def log(*a):
    s = '%s %s' % (time.strftime('%H:%M:%S'), ' '.join(str(x) for x in a))
    print(s); LOG.write(s + '\n'); LOG.flush(); sys.stdout.flush()


GT = [(320, 437), (430, 449), (528, 437), (605, 449), (697, 437)]   # galaxy-map tabs: overlay, economic, events, military, map
LAYOUT = {   # per race UI (game coordinates 800x600); orders=None: fleets only move, no mission screen
    'A': dict(dip=dict(races=(80, 474, 16), propose=(125, 378), acts=[(400, 27), (400, 54), (400, 81), (630, 27), (630, 54), (630, 81)], send=(688, 378), plus=(505, 228)),
              qhead=(638, 270), turn=(163, 33), home=(540, 258), tfx=120, tfy=(300, 345, 385), orders=(100, 568),
              missions=[(285, 258), (285, 330), (285, 372), (430, 330), (430, 372), (285, 397)],
              tabs={'build': (94, 150), 'ships': (94, 178), 'prod': (94, 94)}, buy=(640, 198),
              arrows=((370, 568), (100, 170, 238, 308, 376)), auto=(640, 240), systems=(320, 20),
              syslist=(300, 111, 18), buildlist=113, mapbtn=((610, 304), (625, 328)), gtabs=GT),
    'B': dict(qhead=(638, 280), turn=(110, 22), home=(522, 250), tfx=140, tfy=(305, 345, 385), orders=(110, 563),
              missions=[(545, 268), (550, 294), (390, 369), (370, 394), (340, 419), (330, 444), (310, 519)],
              tabs={'build': (90, 143), 'ships': (90, 171), 'prod': (90, 87)}, buy=(650, 207),
              arrows=((375, 582), (104, 175, 246, 317, 388)), auto=(668, 255), systems=(310, 22),
              syslist=(300, 111, 18), buildlist=113, mapbtn=((660, 356), (660, 380)),
              gtabs=[(320, 437), (430, 449), (528, 437), (600, 440), (697, 437)]),
    'C': dict(dip=dict(races=(95, 473, 16), propose=(130, 372), acts=[(440, 18), (440, 49), (440, 80), (585, 18), (585, 49), (585, 80)], send=(515, 426), plus=(480, 178)),
              qhead=(640, 272), turn=(130, 22), home=(560, 258), tfx=140, tfy=(277, 317, 357), orders=(110, 563), missions=[],
              menu=(280, 327, 20, 12), mapbtn=((627, 362), (627, 384)),
              tabs={'build': (90, 150), 'ships': (90, 178), 'prod': (90, 91)}, buy=(650, 195),
              arrows=((375, 578), (101, 170, 239, 308, 376)), auto=(715, 238), systems=(300, 18),
              syslist=(290, 85, 17), buildlist=87, gtabs=[(310, 444), (415, 444), (510, 444), (605, 444), (700, 444)]),
    'D': dict(qhead=(648, 262), turn=(150, 22), home=(540, 125), tfx=140, tfy=(272, 312, 352), orders=(140, 568),
              missions=[(370, 369), (370, 391), (370, 413), (370, 436), (370, 459), (370, 481),
                        (570, 369), (570, 391), (570, 413), (570, 436), (570, 459)], noscrap=[(570, 413)],
              tabs={'build': (85, 149), 'ships': (85, 178), 'prod': (150, 91)}, buy=(655, 195),
              arrows=((358, 573), (101, 173, 243, 320, 390)), auto=(740, 235), systems=(340, 18),
              syslist=(310, 98, 17), buildlist=82, gtabs=[(295, 437), (400, 444), (510, 447), (615, 444), (720, 437)]),
    'E': dict(dip=dict(races=(85, 470, 16), propose=(115, 372), acts=[(365, 20), (365, 48), (365, 76), (645, 20), (645, 48), (645, 76)], send=(440, 407), plus=(538, 173)),
              qhead=(640, 272), turn=(180, 22), home=(540, 255), tfx=140, tfy=(260, 300, 340), orders=(110, 563), missions=[],
              menu=(265, 306, 19, 11), mapbtn=((712, 365), (712, 385)), noscrap=[(265, 458)],
              tabs={'build': (115, 160), 'ships': (115, 188), 'prod': (130, 102)}, buy=(690, 196),
              arrows=((368, 570), (107, 176, 243, 315, 381)), auto=(740, 240), systems=(320, 18),
              syslist=(290, 127, 18), buildlist=89, gtabs=[(320, 437), (410, 437), (505, 437), (600, 437), (690, 437)]),
}
L = dict(LAYOUT[INST])
if '--home' in sys.argv:
    L['home'] = tuple(int(v) for v in sys.argv[sys.argv.index('--home') + 1].split(','))
TABS = L['gtabs']


def stopped():
    return os.path.exists(STOP) or not H.pid_alive(PID)


def key(vk):
    act('key %#x' % vk)
    hw = H.main_window(PID); H.user32.PostMessageW(hw, 0x100, vk, 1); nap(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)


def click(xy, wait=0.35):
    act('click %d,%d' % tuple(xy))
    H.click(H.main_window(PID), xy[0], xy[1], pid=PID); nap(wait)


def hold(xy, t=0.5):
    # labor arrows react only to a held button
    act('hold %d,%d %.1fs' % (xy[0], xy[1], t))
    hw = H.main_window(PID)
    H.set_cursor(PID, *xy); nap(0.15); cx, cy = H.game2client(hw, *xy)
    H.user32.PostMessageW(hw, H.WM_MOUSEMOVE, 0, H.lparam(cx, cy)); nap(0.05)
    H.user32.PostMessageW(hw, H.WM_LBUTTONDOWN, H.MK_LBUTTON, H.lparam(cx, cy)); time.sleep(t)   # hold time is not scaled
    H.user32.PostMessageW(hw, H.WM_LBUTTONUP, 0, H.lparam(cx, cy)); nap(0.4)


def credits():
    emp = H.readmem(PID, 0x5a2b2a, 1)[0]
    return struct.unpack('<i', H.readmem(PID, 0x5b1b30 + emp * 0x1bc, 4))[0]


MENU_IMG = None


def menu_open():
    global MENU_IMG
    from PIL import Image, ImageChops, ImageStat
    if MENU_IMG is None:
        MENU_IMG = Image.open(os.path.join(TPL, 'mainmenu_continue.png')).convert('RGB')
    img = screen(INST, PID, 'pl_menu').convert('RGB')
    return sum(ImageStat.Stat(ImageChops.difference(img.crop((655, 105, 780, 140)), MENU_IMG)).mean) / 3 < 25


def menu_guard():
    # the in-game main menu has RETIRE/QUIT where the galaxy-map tabs are; never click into it
    if menu_open():
        act('main menu open -> CONTINUE'); click((705, 122), 1.5)


def esc_safe():
    # leave sub screens with F1 (galaxy map) instead of Escape: Escape on the galaxy map opens the main menu
    key(0x70); nap(0.6)
    menu_guard()


def browse(n=None):
    menu_guard()
    acts = []
    for _ in range(n if n is not None else (rnd.randint(6, 12) if HEAVY else rnd.randint(1, 4))):
        r = rnd.random()
        if r < 0.55:
            xy = rnd.choice(TABS); click(xy, 0.1); acts.append('tab%d' % xy[0])
        elif r < 0.8:
            vk = rnd.choice([0x71, 0x72, 0x73]); key(vk); nap(0.4); key(0x70); acts.append('F%d' % (vk - 0x6f))
        else:
            key(0x70); acts.append('F1')
        nap(rnd.uniform(0.1, 0.6))
    return acts


EMBLEM = EMBLEM_SMALL = None
MENU_BOX = (130, 280, 400, 560)                 # area of the fleet orders menu (all races)


def mission_rows():
    # all rows of the fleet orders menu except SCRAP (agents scrapped their own fleets away: no wars)
    rows = list(L['missions']) if L.get('missions') else []
    if not rows and L.get('menu'):
        x, y0, dy, n = L['menu']
        rows = [(x, y0 + dy * k) for k in range(n)]
    return [r for r in rows if r not in L.get('noscrap', [])]


def fleets():
    # find own task forces on the galaxy map by the race emblem, select one and either set a course to a
    # nearby sector or give it a mission from the ORDERS menu (attack, raid, colonize, terraform, scrap, ...)
    global EMBLEM, EMBLEM_SMALL
    from PIL import Image, ImageChops, ImageStat
    import mapfind
    if EMBLEM is None:
        EMBLEM = Image.open(os.path.join(TPL, 'emblem', '%s.png' % INST)).convert('RGB')
        p = os.path.join(TPL, 'emblem', '%s_small.png' % INST)
        EMBLEM_SMALL = Image.open(p).convert('RGB') if os.path.exists(p) else None
    acts = []

    def view(large):
        # MAP tab -> SMALL/LARGE MAP, then MILITARY (only that view shows the fleets)
        if L.get('mapbtn'):
            click(TABS[4], 0.6); click(L['mapbtn'][1 if large else 0], 0.8)
        click(TABS[3], 0.5)

    key(0x70); nap(0.5)
    view(False)
    for _ in range(rnd.randint(1, 4)):
        if rnd.random() < 0.25:                                # look around: scroll the map a bit
            k = rnd.choice([0x25, 0x26, 0x27, 0x28])
            for _ in range(rnd.randint(1, 4)):
                key(k); nap(0.1)
            acts.append('scroll%x' % k)
        icons = mapfind.find(screen(INST, PID, 'pl_map').convert('RGB'), EMBLEM)
        if not icons and EMBLEM_SMALL is not None and L.get('mapbtn'):
            # none in view: pick one on the whole-galaxy map; going back centres the small map on it
            view(True)
            small = mapfind.find(screen(INST, PID, 'pl_lmap').convert('RGB'), EMBLEM_SMALL, thresh=25, m=2)
            if small:
                sx, sy = rnd.choice(small); click((sx, sy), 0.8); acts.append('lmap%d,%d' % (sx, sy))
            view(False)
            icons = mapfind.find(screen(INST, PID, 'pl_map').convert('RGB'), EMBLEM)
            icons.sort(key=lambda p: abs(p[0] - 541) + abs(p[1] - 261))
            icons = icons[:1]
        if not icons and HOME_IDX is not None:
            open_home(); key(0x70); nap(0.6); view(False)                 # selecting the home system centres the map on it
            icons = mapfind.find(screen(INST, PID, 'pl_map').convert('RGB'), EMBLEM)
            acts.append('home')
        if not icons:
            acts.append('nofleet'); continue
        x, y = rnd.choice(icons)
        if ASSAULT and rnd.random() < 0.7:
            # war in earnest: take the own fleet on screen that is closest to a foreign system and keep pushing it
            try:
                best = min(((targeted_course(ix, iy, icons), (ix, iy)) for ix, iy in icons),
                           key=lambda t: t[0][2] if t[0] else 1e9)
                if best[0]:
                    x, y = best[1]
            except OSError:
                pass
        click((x, y), 0.8); acts.append('fleet%d,%d' % (x, y))     # selects the sector and its first task force
        r = rnd.random()
        try:
            tc = targeted_course(x, y, icons) if ASSAULT and r < 0.55 and rnd.random() < 0.85 else None
        except OSError:                                     # memory moved under us: plain course instead
            tc = None
        if tc:
            click(tc[0], 0.6); acts.append('ATTACKCOURSE%d,%d->sys%d' % (tc[0][0], tc[0][1], tc[1]))
        elif r < 0.55:
            dst = (min(760, max(270, x + 61 * rnd.randint(-4, 4))), min(410, max(50, y + 61 * rnd.randint(-3, 3))))
            click(dst, 0.6); acts.append('course%d,%d' % dst)
        elif r < 0.8 and mission_rows():
            click(L['orders'], 1.0)
            before = screen(INST, PID, 'pl_menu1').convert('RGB').crop(MENU_BOX)
            m = rnd.choice(mission_rows()); click(m, 0.8); acts.append('mission%d,%d' % m)
            after = screen(INST, PID, 'pl_menu2').convert('RGB').crop(MENU_BOX)
            if sum(ImageStat.Stat(ImageChops.difference(before, after)).mean) / 3 < 8:   # disabled row: menu still open
                click(L['orders'], 0.8); acts.append('menuclose')
        key(0x70); nap(0.4)
    return acts


DELYES = None


def replan():
    # a player changes his mind: delete the build at the head of the queue (answer YES when the game asks
    # because industry is invested) and pick something else
    global DELYES
    from PIL import Image, ImageChops, ImageStat
    import json
    if DELYES is None:
        cfg = json.load(open(os.path.join(TPL, 'delyes.json')))[INST]
        DELYES = (cfg, Image.open(os.path.join(TPL, 'delyes_%s.png' % INST)).convert('RGB'))
    cfg, tpl = DELYES
    click(L['qhead'], 1.2)
    img = screen(INST, PID, 'pl_del').convert('RGB')
    d = sum(ImageStat.Stat(ImageChops.difference(img.crop(tuple(cfg['box'])), tpl)).mean) / 3
    acts = ['delhead']
    if d < 20:
        click(tuple(cfg['yes']), 1.0); acts.append('YES')
    click((300, L['buildlist'] + 16 * rnd.randint(0, 6)), 0.6); acts.append('newbuild')
    return acts


def production():
    acts = []
    open_home()
    click(L['tabs']['build'], 0.6)
    if rnd.random() < 0.3:
        acts += replan()
    for _ in range(rnd.randint(1, 3)):                         # keep the main world's queue full
        click((300, L['buildlist'] + 16 * rnd.randint(0, 5)), 0.5); acts.append('build')
    for _ in range(rnd.choice([0, 1, 1, 2])):                 # warships: wars need fleets
        click(L['tabs']['ships'], 0.6); click((300, L['buildlist'] + 16 * rnd.randint(0, 3)), 0.5); acts.append('ship')
    if credits() > 3000 and rnd.random() < (0.7 if credits() > 100000 else 0.3):   # no buying into debt
        click(L['buy'], 0.5); acts.append('buy')
    if rnd.random() < 0.5:                                     # labor at the home system
        click(L['tabs']['prod'], 0.6)
        for _ in range(rnd.randint(1, 3)):
            side = rnd.randint(0, 1); row = rnd.randint(0, 4)
            hold((L['arrows'][0][side], L['arrows'][1][row]), rnd.uniform(0.2, 0.8)); acts.append('labor%d%s' % (row, '-+'[side]))
    if rnd.random() < 0.08:
        click(L['auto'], 0.6); acts.append('autotoggle')
    if rnd.random() < 0.6:                                     # a colony
        click(L['systems'], 0.9); k = rnd.randint(0, 3); click((L['syslist'][0], L['syslist'][1] + L['syslist'][2] * k), 0.9)
        click(L['tabs']['build'], 0.6); acts.append('colony%d' % k)
        if rnd.random() < 0.3:
            acts += replan()
        else:
            click((300, L['buildlist'] + 16 * rnd.randint(0, 6)), 0.5)
        if credits() > 3000 and rnd.random() < 0.3:
            click(L['buy'], 0.5); acts.append('colonybuy')
        if rnd.random() < 0.3:
            click(L['tabs']['prod'], 0.6)
            hold((L['arrows'][0][rnd.randint(0, 1)], L['arrows'][1][rnd.randint(0, 4)]), 0.5); acts.append('colonylabor')
    esc_safe(); key(0x70); nap(0.4)
    return acts


def diplomacy():
    # F5 diplomacy: pick a known race and propose something (friendship / peace, request, gift, affiliation /
    # alliance, membership / war pact, now and then declare war), add credits to gifts, SEND
    d = L.get('dip')
    if not d:
        return []
    acts = []
    key(0x70); nap(0.4); key(0x74); nap(1.2)
    x, y0, dy = d['races']
    k = rnd.randint(0, 3); click((x, y0 + dy * k), 0.6); acts.append('race%d' % k)
    click(d['propose'], 0.6)
    a = rnd.choices(range(6), weights=[25, 10, 30, 15, 15, 40 if ASSAULT else 5])[0]   # assault: wars more often
    click(d['acts'][a], 0.9); acts.append(['friend', 'request', 'gift', 'affil', 'member', 'WAR'][a])
    if a == 2:
        for _ in range(rnd.randint(1, 4)):
            click(d['plus'], 0.2)
    click(d['send'], 0.9); acts.append('send')
    key(0x70); nap(0.4)
    return acts


def in_blame_dialog():
    """intel blame choice shown inside the turn processing (FUN_0047d9b4 -> FUN_00506910, return 0x47dc7f on the
    main thread's stack): the owner of a successful human intel operation picks whom to incriminate"""
    import ctypes
    from dbg import WOW64_CONTEXT, k32, rpm
    from sampler import threads
    hp = k32.OpenProcess(0x1F0FFF, False, PID); th = k32.OpenThread(0x1F03FF, False, threads(PID)[0])
    try:
        k32.SuspendThread(th)
        ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
        k32.Wow64GetThreadContext(th, ctypes.byref(ctx)); stk = rpm(hp, ctx.Esp, 0x2000)
    finally:
        k32.ResumeThread(th); k32.CloseHandle(th); k32.CloseHandle(hp)
    return any(struct.unpack_from('<I', stk, o)[0] == 0x47dc7f for o in range(0, len(stk) - 3, 4))


def turn(): return u32(PID, TURN_ADDR)
def busy(): return i32(PID, BUSY_ADDR)


def press(t):
    for attempt in range(8):
        if busy() != 0 or turn() > t:
            return True
        key(0x70); nap(0.4)
        if not handle_dialogs(dlg, INST, PID, log) and attempt >= 2:
            act('generic_dismiss (Escape)'); generic_dismiss(INST, PID, log); menu_guard()
        act('TURN click'); H.click(H.main_window(PID), *L['turn'], pid=PID)
        for _ in range(10):
            nap(0.3)
            if busy() != 0 or turn() > t:
                return True
    return False


HOME_IDX = None
LAST_REC = None


def home_record():
    if HOME_IDX is None:
        return None
    s = H.readmem(PID, struct.unpack('<I', H.readmem(PID, 0x5a36c8, 4))[0] + HOME_IDX * 0x328 + 0x80, 0x14)
    return s


def find_home():
    # the player's main production world = own system with the highest industry (+0x2c4)
    global HOME_IDX
    loc = H.readmem(PID, 0x5a2b2a, 1)[0]
    sp = struct.unpack('<I', H.readmem(PID, 0x5a36c8, 4))[0]; n = struct.unpack('<H', H.readmem(PID, 0x5a36bc, 2))[0]
    raw = H.readmem(PID, sp, n * 0x328)
    own = [(struct.unpack_from('<h', raw, i * 0x328 + 0x2c4)[0], i) for i in range(n) if raw[i * 0x328 + 0x4c] == loc]
    HOME_IDX = max(own)[1] if own else None
    log('home system index', HOME_IDX, raw[HOME_IDX * 0x328 + 8:HOME_IDX * 0x328 + 0x28].split(bytes(1))[0] if own else '')


def home_lost():
    # the home world was conquered, rebelled or died out: pick a new one (a real player would not open a lost
    # system either; writing a foreign system into the system screen selection is not a normal game state)
    sp = struct.unpack('<I', H.readmem(PID, 0x5a36c8, 4))[0]
    return H.readmem(PID, sp + HOME_IDX * 0x328 + 0x4c, 1)[0] != H.readmem(PID, 0x5a2b2a, 1)[0]


def sectors_w():
    return {0: 13, 1: 16, 2: 25}.get(struct.unpack('<I', H.readmem(PID, 0x5a36b8, 4))[0], 13)


def system_at(x, y):
    # FUN_0043dab0: sector record [0x5a36d8] + (W*x + y) * 0x68, system index word at +0xc (-1: none)
    sec = struct.unpack('<I', H.readmem(PID, 0x5a36d8, 4))[0] + (sectors_w() * x + y) * 0x68
    return struct.unpack('<h', H.readmem(PID, sec + 0xc, 2))[0]


def ui_fleets():
    # the UI copy of the task forces [0x5b2358] (what the fleet screens edit; END TURN turns differences into
    # fleet orders, FUN_004667d0): record 0x6c, +0x2c mission, +0x30 mission parameter, +0x34 owner, +0x38 x, +0x3c y
    obj = struct.unpack('<I', H.readmem(PID, 0x5b2358, 4))[0]
    base, size, n = struct.unpack('<I', H.readmem(PID, obj + 0x20, 4))[0], struct.unpack('<I', H.readmem(PID, obj + 0x10, 4))[0],         struct.unpack('<I', H.readmem(PID, obj + 0x18, 4))[0]
    raw = H.readmem(PID, base, size * n)
    return [(base + i * size, raw[i * size:(i + 1) * size]) for i in range(n)]


MAP_L, MAP_T, CELL, MAP_COLS, MAP_ROWS = 269, 49.5, 60.5, 8, 6        # small galaxy map: grid origin, cell size


def sector_systems():
    # system index of every sector: [0x5a36d8] + (25*row + col) * 0x68 (W from the galaxy size), +0xc
    # galaxy width/height from the map view [[0x595554]+0x6c] +0x14/+0x18 (25 x 18 on a large galaxy)
    v = struct.unpack('<I', H.readmem(PID, struct.unpack('<I', H.readmem(PID, 0x595554, 4))[0] + 0x6c, 4))[0]
    W, rows = struct.unpack('<ii', H.readmem(PID, v + 0x14, 8))
    if W != sectors_w() or not 0 < rows <= 40:
        return W, {}
    sec = struct.unpack('<I', H.readmem(PID, 0x5a36d8, 4))[0]
    raw = H.readmem(PID, sec, W * rows * 0x68)
    return W, {(i // W, i % W): struct.unpack_from('<h', raw, i * 0x68 + 0xc)[0] for i in range(W * rows)}


def targeted_course(x, y, icons):
    # the selected own task force (emblem at x, y) flies towards the nearest foreign system. The map origin is
    # found from the emblems on screen: each own task force sits in a known sector (+0x38 row, +0x3c column)
    loc = H.readmem(PID, 0x5a2b2a, 1)[0]
    own = [struct.unpack_from('<ii', r, 0x38) for a, r in ui_fleets() if r[0x34] == loc]
    if not own:
        return None
    cells = [(int((iy - MAP_T) // CELL), int((ix - MAP_L) // CELL)) for ix, iy in icons]
    votes = {}
    for cr, cc in cells:
        for r, c in own:
            votes[(r - cr, c - cc)] = votes.get((r - cr, c - cc), 0) + 1
    (orow, ocol), n = max(votes.items(), key=lambda kv: kv[1])
    sel = (int((y - MAP_T) // CELL) + orow, int((x - MAP_L) // CELL) + ocol)
    if sel not in own:
        return None
    sp = struct.unpack('<I', H.readmem(PID, 0x5a36c8, 4))[0]
    W, systems = sector_systems()
    foreign = [(rc, si) for rc, si in systems.items() if si >= 0
               and H.readmem(PID, sp + si * 0x328 + 0x4c, 1)[0] not in (loc, 0x23)]
    if not foreign:
        return None
    (tr, tc), si = min(foreign, key=lambda f: abs(f[0][0] - sel[0]) + abs(f[0][1] - sel[1]))
    # target cell on screen, clamped to the visible part of the map (fly partway when it is off screen)
    # at most 3 sectors per course (a click outside the fleet's range is ignored by the game), then clamp to
    # the visible part of the map
    step = lambda d: max(-3, min(3, d))
    gr, gc = sel[0] + step(tr - sel[0]), sel[1] + step(tc - sel[1])
    vr = min(MAP_ROWS - 1, max(0, gr - orow)); vc = min(MAP_COLS - 1, max(0, gc - ocol))
    dist = abs(tr - sel[0]) + abs(tc - sel[1])
    return (int(MAP_L + (vc + 0.5) * CELL), int(MAP_T + (vr + 0.5) * CELL)), si, dist


def intel():
    # intelligence screen (F3): redistribute internal security / espionage / sabotage per target. The screen's
    # data [[0x5cb4b4]+0x1c..+0x3c] (security, espionage x4, sabotage x4 in %) is what the sliders write; leaving
    # the screen commits it (0x4bcb90: intel order of type 4 + the player's own intel record)
    key(0x70); nap(0.4); key(0x72); nap(1.0)
    ui = struct.unpack('<I', H.readmem(PID, 0x5cb4b4, 4))[0]
    old = [struct.unpack('<i', H.readmem(PID, ui + 0x1c + 4 * i, 4))[0] for i in range(9)]
    if sum(old) != 100:
        key(0x70); nap(0.4); return ['intel?%s' % old]
    sec = rnd.choice([30, 40, 50, 60, 70, 80, 100])
    vals = [sec] + [0] * 8
    for _ in range((100 - sec) // 10):
        vals[rnd.randint(1, 8)] += 10
    for i, v in enumerate(vals):
        H.writemem(PID, ui + 0x1c + 4 * i, struct.pack('<i', v))
    key(0x70); nap(0.6)
    return ['INTEL%s' % ','.join(map(str, vals))]


def assault():
    # war in earnest: every own task force that stands in a sector with a foreign system gets the invasion
    # mission 0x0e (bombard, then invade with troop transports), "conquer" (+0x30 = 1), exactly what the fleet
    # mission dialog writes (0x4ebd53 / 0x4ebc22); the game sends it as a fleet order at END TURN
    loc = H.readmem(PID, 0x5a2b2a, 1)[0]
    sp = struct.unpack('<I', H.readmem(PID, 0x5a36c8, 4))[0]
    acts = []
    for addr, r in ui_fleets():
        if r[0x34] != loc:
            continue
        mission = struct.unpack_from('<i', r, 0x2c)[0]
        x, y = struct.unpack_from('<ii', r, 0x38)
        s = system_at(x, y)
        if s < 0:
            continue
        owner = H.readmem(PID, sp + s * 0x328 + 0x4c, 1)[0]
        if owner in (loc, 0x23) or mission == 0x0e:
            continue
        H.writemem(PID, addr + 0x2c, struct.pack('<ii', 0x0e, 1 if rnd.random() < 0.8 else 2))
        acts.append('ASSAULT tf%d sys%d(owner %d)' % (struct.unpack_from('<I', r, 0)[0], s, owner))
    return acts


def open_home():
    # galaxy map, select the home world (UI selection [[0x595da8]+0x1c], same effect as clicking it), F2
    key(0x70); nap(0.4)
    if HOME_IDX is not None and HOME_IDX < struct.unpack('<H', H.readmem(PID, 0x5a36bc, 2))[0]:
        ui = struct.unpack('<I', H.readmem(PID, 0x595da8, 4))[0]
        H.writemem(PID, ui + 0x1c, struct.pack('<h', HOME_IDX)); act('select home %d' % HOME_IDX)
    else:
        click(L['home'], 0.5)
    key(0x71); nap(0.8)


def swap_new_build():
    # the turn processing just started the next queue item at the home system; many players replace it
    # right away ("not now") -> delete it (answer YES) and pick something else
    global LAST_REC
    rec = home_record()
    acts = []
    if rec is not None and LAST_REC is not None and rec[0:4] != bytes(4) and rec[8:10] != LAST_REC[8:10]             and rec[0:4] != bytes([5, 0, 0, 0]) and rnd.random() < 0.6:
        open_home()
        click(L['tabs']['build'], 0.6)
        acts = ['newbuild-at-home(%s)' % rec[:12].hex()] + replan()
        key(0x70); nap(0.4)
    LAST_REC = home_record()
    return acts


def main():
    log('player', INST, 'pid', PID, 'heavy' if HEAVY else 'light', 'home', L['home'])
    last = -1
    while not stopped():
        t = turn()
        if t == last or busy() != 0:                           # turn not started yet (or still processing)
            if busy() == 0:
                handle_dialogs(dlg, INST, PID, log)
            nap(0.5); continue
        nap(rnd.uniform(1.5, 4.0))                      # look at the new turn, read events
        handle_dialogs(dlg, INST, PID, log)
        if HOME_IDX is None or home_lost():
            find_home()
        pre = swap_new_build()
        steps = [browse, fleets, production] + ([diplomacy] if rnd.random() < (0.5 if ASSAULT else 0.35) else []) + ([assault] if ASSAULT else []) + ([intel] if ASSAULT and rnd.random() < 0.3 else [])
        if os.path.exists(RESYNC_TURN) and open(RESYNC_TURN).read().strip() == str(t) and diplomacy in steps:
            steps.remove(diplomacy)                          # resync spike finding F: stale diplomacy items until the next turn
        rnd.shuffle(steps)
        acts = list(pre)
        for f in steps:
            if stopped():
                return
            acts += f()
            nap(rnd.uniform(0.3, 2.0))
        if not press(t):
            log('turn %d: TURN press failed' % t); screen(INST, PID, os.path.join('..', out, 'pressfail_%s_t%d' % (INST, t)))
            last = t; continue
        acts.append('TURN')
        t0 = time.time(); waits = 0; idle_same = 0
        while not stopped() and (turn() <= t or busy() != 0):   # wait for the other player and processing
            # a resync transfer (tools/spike.py) loaded the game after TURN: same turn, not waiting any more
            idle_same = idle_same + 1 if busy() == 0 and turn() == t else 0
            if idle_same >= 3:
                log('turn %d: idle again after TURN (resync load), pressing TURN again' % t)
                if not press(t):
                    break
                acts.append('TURN(again)'); idle_same = 0
            if busy() == -1 and rnd.random() < (0.5 if HEAVY else 0.2):
                acts += ['(waiting)' + a for a in browse(rnd.randint(1, 3))]
            elif busy() == 1 and waits < 2 and rnd.random() < 0.3:
                acts += ['(processing)' + a for a in browse(rnd.randint(1, 2))]; waits += 1
            if time.time() - t0 > 6:
                handle_dialogs(dlg, INST, PID, log)
            if busy() == 1 and time.time() - t0 > 15 and in_blame_dialog():
                act('blame: first choice'); H.click(H.main_window(PID), 290, 373, pid=PID); acts.append('(processing)blame')
            nap(rnd.uniform(0.5, 2.0))
        log('turn %d -> %d (%.0fs): %s' % (t, turn(), time.time() - t0, ' '.join(acts)))
        last = t


if __name__ == '__main__':
    main()
