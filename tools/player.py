"""One independent player agent per game window (run one process per instance, in parallel).
Each agent plays its own empire like a person: browses screens, moves fleets, changes labor and
production, sometimes buys, presses TURN when done and keeps clicking around while it waits for the
other player and while the turn is processed. tools/observer.py traces and compares both games.
usage: player.py <A..E> <seed> <logdir> [--heavy] [--home X,Y]
  --heavy   this player checks the galaxy-map tabs several times per turn
Stops when <logdir>/stop exists."""
import os, random, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import (u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, ACTIVE_ADDR, Dialogs, handle_dialogs,
                      generic_dismiss, screen, TPL)

INST, seed, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
HEAVY = '--heavy' in sys.argv
os.makedirs(out, exist_ok=True)
rnd = random.Random(seed * 10 + ord(INST))
PID = H.load_state()[INST]
dlg = Dialogs()
STOP = os.path.join(out, 'stop')
SPEED = float(os.environ.get('BOTF_SPEED', '0.4'))   # scales every pause of the agent (1.0 = slow, human-like)


def nap(t):
    time.sleep(max(0.05, t * SPEED))
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
    'A': dict(qhead=(638, 270), turn=(163, 33), home=(540, 258), tfx=120, tfy=(300, 345, 385), orders=(100, 568),
              missions=[(285, 258), (285, 330), (285, 372), (430, 330), (430, 372), (285, 397)],
              tabs={'build': (94, 150), 'ships': (94, 178), 'prod': (94, 94)}, buy=(640, 198),
              arrows=((370, 568), (100, 170, 238, 308, 376)), auto=(640, 240), systems=(320, 20),
              syslist=(300, 111, 18), buildlist=113, gtabs=GT),
    'B': dict(qhead=(638, 280), turn=(110, 22), home=(522, 250), tfx=140, tfy=(305, 345, 385), orders=(110, 563),
              missions=[(545, 268), (550, 294), (390, 369), (370, 394), (340, 419), (330, 444), (310, 519)],
              tabs={'build': (90, 143), 'ships': (90, 171), 'prod': (90, 87)}, buy=(650, 207),
              arrows=((375, 582), (104, 175, 246, 317, 388)), auto=(668, 255), systems=(310, 22),
              syslist=(300, 111, 18), buildlist=113, gtabs=GT),
    'C': dict(qhead=(640, 272), turn=(130, 22), home=(560, 258), tfx=140, tfy=(277, 317, 357), orders=None, missions=[],
              tabs={'build': (90, 150), 'ships': (90, 178), 'prod': (90, 91)}, buy=(650, 195),
              arrows=((375, 578), (101, 170, 239, 308, 376)), auto=(715, 238), systems=(300, 18),
              syslist=(290, 85, 17), buildlist=87, gtabs=[(310, 444), (415, 444), (510, 444), (605, 444), (700, 444)]),
    'D': dict(qhead=(648, 262), turn=(150, 22), home=(540, 125), tfx=140, tfy=(272, 312, 352), orders=None, missions=[],
              tabs={'build': (85, 149), 'ships': (85, 178), 'prod': (150, 91)}, buy=(655, 195),
              arrows=((358, 573), (101, 173, 243, 320, 390)), auto=(740, 235), systems=(340, 18),
              syslist=(310, 98, 17), buildlist=82, gtabs=[(295, 437), (400, 444), (510, 447), (615, 444), (720, 437)]),
    'E': dict(qhead=(640, 272), turn=(180, 22), home=(540, 255), tfx=140, tfy=(260, 300, 340), orders=None, missions=[],
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


def fleets():
    acts = []
    key(0x70); nap(0.5)
    for _ in range(rnd.randint(1, 3)):
        click(L['home'], 0.6)
        click((L['tfx'], rnd.choice(L['tfy'])), 0.5)
        r = rnd.random()
        if r < 0.2:                                            # most fleets stay home and defend
            dst = (rnd.randint(275, 745), rnd.randint(50, 400)); click(dst, 0.5); acts.append('move%d,%d' % dst)
        elif r < 0.5 and L['orders']:
            click(L['orders'], 0.9); m = rnd.choice(L['missions']); click(m, 0.6); acts.append('mission%d,%d' % m)
            esc_safe(); key(0x70); nap(0.4)
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
    if rnd.random() < 0.5:
        click(L['tabs']['ships'], 0.6); click((300, L['buildlist'] + 16 * rnd.randint(0, 2)), 0.5); acts.append('ship')
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
        if HOME_IDX is None:
            find_home()
        pre = swap_new_build()
        steps = [browse, fleets, production]
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
        t0 = time.time(); waits = 0
        while not stopped() and (turn() <= t or busy() != 0):   # wait for the other player and processing
            if busy() == -1 and rnd.random() < (0.5 if HEAVY else 0.2):
                acts += ['(waiting)' + a for a in browse(rnd.randint(1, 3))]
            elif busy() == 1 and waits < 2 and rnd.random() < 0.3:
                acts += ['(processing)' + a for a in browse(rnd.randint(1, 2))]; waits += 1
            if time.time() - t0 > 6:
                handle_dialogs(dlg, INST, PID, log)
            nap(rnd.uniform(0.5, 2.0))
        log('turn %d -> %d (%.0fs): %s' % (t, turn(), time.time() - t0, ' '.join(acts)))
        last = t


if __name__ == '__main__':
    main()
