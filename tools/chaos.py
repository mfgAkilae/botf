"""Random UI activity on both instances before and DURING turn processing; diff state after each turn.
usage: chaos.py <nturns> [seed] [--during-only] [--before-only]
Stops at the first turn with state differences."""
import os, random, struct, subprocess, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import (u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, snapshot, compare, force_active,
                      Dialogs, handle_dialogs)

st = H.load_state(); P = {'A': st['A'], 'B': st['B']}
n = int(sys.argv[1]); rnd = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1)
during = '--before-only' not in sys.argv
before = '--during-only' not in sys.argv
dlg = Dialogs()
HERE = os.path.dirname(os.path.abspath(__file__)); TL = os.path.join(HERE, '..', 'turnlog')
LOG = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'turnlog', 'chaos.log'), 'a')

def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n'); LOG.flush(); sys.stdout.flush()

def key(inst, vk):
    hw = H.main_window(P[inst])
    H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)

TABS = [(320, 437), (430, 449), (528, 437), (605, 449), (697, 437), (167, 68)]
SYS_TABS = [(94, 94), (94, 122), (94, 150), (94, 178), (94, 206)]

MENU = None
def leave_menu(inst):
    # Escape can open the in-game main menu; never click around in it (NEW GAME etc.)
    global MENU
    from PIL import Image, ImageChops, ImageStat
    from autoturn import screen, TPL
    if MENU is None:
        MENU = Image.open(os.path.join(TPL, 'mainmenu_continue.png')).convert('RGB')
    for _ in range(3):
        img = screen(inst, P[inst], 'menu').convert('RGB')
        d = ImageStat.Stat(ImageChops.difference(img.crop((655, 105, 780, 140)), MENU)).mean
        if sum(d) / 3 >= 25:
            return
        H.click(H.main_window(P[inst]), 705, 122, pid=P[inst]); time.sleep(1.5)

def action(inst):
    r = rnd.random()
    hw = H.main_window(P[inst])
    if r < 0.25:
        vk = rnd.choice([0x70, 0x71, 0x72, 0x73, 0x74]); key(inst, vk); return 'key%x' % vk
    if r < 0.40:
        x, y = rnd.choice(TABS); H.click(hw, x, y, pid=P[inst]); return 'tab%d,%d' % (x, y)
    if r < 0.50:
        x, y = rnd.choice(SYS_TABS); H.click(hw, x, y, pid=P[inst]); return 'sys%d,%d' % (x, y)
    if r < 0.85:
        x, y = rnd.randint(260, 760), rnd.randint(45, 405)
        m = rnd.random()
        H.click(hw, x, y, right=m < 0.2, pid=P[inst])
        if 0.2 <= m < 0.5:
            time.sleep(0.04); H.click(hw, x, y, pid=P[inst]); return 'dbl%d,%d' % (x, y)
        return ('r' if m < 0.2 else 'clk') + '%d,%d' % (x, y)
    if r < 0.93:
        key(inst, 0x1b); time.sleep(0.6); leave_menu(inst); return 'esc'
    x, y = rnd.randint(20, 220), rnd.randint(140, 420)
    H.click(hw, x, y, pid=P[inst]); return 'left%d,%d' % (x, y)

def home(inst):
    key(inst, 0x1b); time.sleep(0.5); leave_menu(inst); key(inst, 0x70); time.sleep(0.8)
    # leave in-game main menu if Escape opened it
    from autoturn import generic_dismiss

def pressed(inst, t):
    return i32(P[inst], BUSY_ADDR) != 0 or u32(P[inst], TURN_ADDR) > t

def press(inst, t):
    for attempt in range(8):
        if pressed(inst, t):
            return True
        handle_dialogs(dlg, inst, P[inst], log)
        key(inst, 0x1b); time.sleep(0.4); key(inst, 0x70); time.sleep(0.8)
        from autoturn import generic_dismiss, screen
        if attempt >= 2:
            generic_dismiss(inst, P[inst], log)
        H.click(H.main_window(P[inst]), *TURN_BTN[inst], pid=P[inst])
        for _ in range(10):
            time.sleep(0.3)
            if pressed(inst, t):
                return True
    return False

for k in range(n):
    force_active(P)
    t = u32(P['A'], TURN_ADDR)
    acts = []
    if before:
        for _ in range(rnd.randint(3, 10)):
            inst = rnd.choice('AB'); acts.append(inst + ':' + action(inst)); time.sleep(rnd.uniform(0.1, 0.6))
    ra, rb = H.readmem(P['A'], 0x596bac, 0x120), H.readmem(P['B'], 0x596bac, 0x120)
    if ra[:4] + ra[0x18:] != rb[:4] + rb[0x18:]:
        log('RNG differs BEFORE turn %d after idle actions: %s' % (t, ' '.join(acts))); break
    trace = '--trace' in sys.argv or '--ktrace' in sys.argv
    if trace:
        stopf = os.path.join(TL, 'tracer.stop')
        if os.path.exists(stopf): os.remove(stopf)
        env = dict(os.environ, STACK='8', TRACER_STOP=stopf, ONLY2='1')
        for inst in 'AB':
            if '--ktrace' in sys.argv:
                cmd = [sys.executable, '-I', '-u', os.path.join(HERE, 'ktrace.py'), str(P[inst]), '900']
            else:
                cmd = [sys.executable, '-I', '-u', os.path.join(HERE, 'tracer.py'), str(P[inst]), '900',
                       '507e50=e50', '507ff0=ff0', '507d10=d10', '507ab0=ab0', '507b70=b70']
            subprocess.Popen(cmd, stdout=open(os.path.join(TL, 'rng_t%03d_%s.log' % (t, inst)), 'w'), stderr=subprocess.STDOUT, env=env)
        time.sleep(2.5)
    if not press('B', t):
        log('STOP: B press failed'); break
    if before:
        for _ in range(rnd.randint(0, 5)):
            acts.append('A:' + action('A')); time.sleep(rnd.uniform(0.1, 0.5))
    if not press('A', t):
        log('STOP: A press failed'); break
    t0 = time.time(); last = time.time(); result = None
    while True:
        if not (H.pid_alive(P['A']) and H.pid_alive(P['B'])):
            result = 'dead'; break
        force_active(P)
        ta, tb = u32(P['A'], TURN_ADDR), u32(P['B'], TURN_ADDR)
        ba, bb = i32(P['A'], BUSY_ADDR), i32(P['B'], BUSY_ADDR)
        if ta > t and tb > t and ba == 0 and bb == 0:
            result = 'ok'; break
        if during and rnd.random() < 0.7:
            inst = rnd.choice('AB')
            if i32(P[inst], BUSY_ADDR) != 0:
                acts.append(inst + '*:' + action(inst))
        if time.time() - t0 > 3:
            if handle_dialogs(dlg, 'A', P['A'], log) + handle_dialogs(dlg, 'B', P['B'], log):
                last = time.time()
        if time.time() - last > 120:
            result = 'stuck'; break
        time.sleep(rnd.uniform(0.05, 0.4))
    time.sleep(1.5)
    if trace:
        open(stopf, 'w').close(); time.sleep(3)
    rep = compare(snapshot(P['A']), snapshot(P['B'])) if result == 'ok' else []
    log('turn %d -> %d: %s in %.1fs | diffs %d | actions %d' % (t, t + 1, result, time.time() - t0, len(rep), len(acts)))
    log('   acts: ' + ' '.join(acts))
    for x in rep[:12]:
        log('    ', x)
    if result == 'ok':
        try:
            import ordercmp
            od, _, _ = ordercmp.compare(P['A'], P['B'])
            if od:
                log('   ORDER LIST DIFFERS (%d):' % len(od))
                for x in od[:8]: log('      ' + x)
        except Exception as e:
            log('   ordercmp failed: %s' % e)
    hb = [x for x in rep if x.startswith(('RNG differs', 'CRC vars differ', 'turn differs'))]
    if '--hb' in sys.argv and result == 'ok' and rep and not hb:
        log('   (state diffs without heartbeat mismatch, continuing)')
        rep = []
    if result != 'ok' or rep:
        if hb:
            log('HB MISMATCH at turn %d' % (t + 1))
        break
    if trace and '--ktrace' not in sys.argv:
        for inst in 'AB':
            try: os.remove(os.path.join(TL, 'rng_t%03d_%s.log' % (t, inst)))
            except OSError: pass
    home('A'); home('B')
