"""Play manual tactical combats: for every instance whose screen shows the tactical view, click around (select
ships, targets, the order wheel, views) and press TURN; answer the pre-combat dialog with FIGHT, HAIL or AUTO.
Runs until <seconds> pass or <logdir>/stop exists. One process handles all instances.
usage: tactical.py <seconds> <logdir> [seed]"""
import os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import screen
from PIL import Image, ImageChops, ImageStat

dur, out = float(sys.argv[1]), sys.argv[2]
rnd = random.Random(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
stopf = os.path.join(out, 'stop')
LOG = open(os.path.join(out, 'tactical.log'), 'a')
# per race: TURN button in the tactical view, a pixel box that identifies the view (left panel 'PLAYBACK/TACTICAL'),
# pre-combat dialog buttons (fight, hail, auto) and the order wheel area
UI = {
    'B': dict(turn=(95, 25), wheel=(95, 230), autobtn=(135, 413)),
    'E': dict(turn=(95, 25), wheel=(95, 230), autobtn=(135, 413)),
    'C': dict(turn=(80, 22), wheel=(97, 260), autobtn=(128, 415)),
    'A': dict(turn=(95, 35), wheel=(95, 245), autobtn=(125, 419), optbox=(10, 55, 185, 85)),
    'D': dict(turn=(100, 22), wheel=(97, 255), autobtn=(138, 414)),
}
REF = {}
ROUNDS = {}


def log(*a):
    s = '%s %s' % (time.strftime('%H:%M:%S'), ' '.join(str(x) for x in a)); print(s); LOG.write(s + '\n'); LOG.flush()


def tactical_view(img, x):
    # the tactical view's left column starts with TURN/END and OPTIONS; no strategic screen has OPTIONS there.
    # tpl/tactical_<X>.png = the OPTIONS button (10,45)-(185,75) cut from a tactical screenshot of that race
    r = REF.get(x)
    box = UI.get(x, {}).get('optbox', (10, 45, 185, 75))
    return r is not None and sum(ImageStat.Stat(ImageChops.difference(img.crop(box), r)).mean) / 3 < 20


def dialog_seen(img):
    # unknown race layout: the pre-combat dialog text starts with "Combat occurring" (blue on black)
    return False


def main():
    st = H.load_state(); P = {k: st[k] for k in 'ABCDE' if k in st and H.pid_alive(st[k])}
    for x in P:
        p = os.path.join(H.TPL if hasattr(H, 'TPL') else os.path.join(os.path.dirname(__file__), '..', 'tpl'), 'tactical_%s.png' % x)
        if os.path.exists(p):
            REF[x] = Image.open(p).convert('RGB')
    t0 = time.time(); n = 0
    while time.time() - t0 < dur and not os.path.exists(stopf):
        for x, pid in P.items():
            if not H.pid_alive(pid):
                continue
            img = screen(x, pid, 'tac').convert('RGB')
            if not tactical_view(img, x):
                if x not in REF and dialog_seen(img):
                    log('%s: combat on screen but no tactical_%s.png reference yet' % (x, x))
                continue
            hw = H.main_window(pid); acts = []
            # Enter closes info dialogs such as "Cloaked ships get a free move. Click CLOSE to review turn."
            H.user32.PostMessageW(hw, 0x100, 0x0d, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x0d, 0xC0000001)
            time.sleep(0.3)
            for _ in range(rnd.randint(2, 8)):
                r = rnd.random()
                if r < 0.15:
                    xy = (rnd.randint(10, 185), rnd.randint(140, 160))       # TACTICAL toggle (ship info / wheel)
                elif r < 0.5:
                    xy = (rnd.randint(200, 790), rnd.randint(10, 490))         # a ship / target / empty space
                elif r < 0.85:
                    c = UI[x]['wheel']; xy = (c[0] + rnd.randint(-75, 75), c[1] + rnd.randint(-55, 55))   # order wheel
                else:
                    xy = (rnd.randint(20, 180), rnd.randint(380, 480))       # reset/views/status/fleets/enemy
                H.click(hw, *xy, pid=pid); time.sleep(0.25); acts.append('%d,%d' % xy)
            ROUNDS[x] = ROUNDS.get(x, 0) + 1
            if ROUNDS[x] % 6 == 0:                                       # let the computer finish long combats
                H.click(hw, *UI[x]['autobtn'], pid=pid); time.sleep(0.4); acts.append('AUTO')
            H.click(hw, *UI[x]['turn'], pid=pid); n += 1
            log('%s tactical turn %d: %s' % (x, n, ' '.join(acts)))
        time.sleep(1.0)


if __name__ == '__main__':
    main()
