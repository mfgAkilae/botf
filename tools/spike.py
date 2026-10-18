"""Driver for the resync spike (docs/resync_design_draft.md section 7) on a test bed running a --spike build.
usage:
  spike.py status                         state, counters, CRC words and normalised RNG of every instance
  spike.py log [inst ...]                 decoded spike log
  spike.py rx <inst> [n]                  last n received 0x400 notifications, sender mapped to the player table
  spike.py run [opts]                     one transfer: PREPARE (host), ARMED (all), SEND (host), wait for DONE
      --host X          host instance (default A)
      --diverge X:S[:D] before the transfer add D (default 7) to the morale word +0x2dc of system S on client X
      --badcrc X        give client X a wrong expected CRC32 (procedure 6: rejected, no load)
      --nofile          rename the host's auto.sav between PREPARE and SEND (procedure 6: missing file)
      --keep            do not compare game state with the host after the transfer
      --endturn X       X ends its turn before the transfer (procedure 2: X waits with BUSY -1)
      --inactive X,Y    mark these windows inactive ([0x5a28d4] = 0) before ARMED: nested pumps would wait, the
                        pump override must exit them (procedure 4); afterwards they are made active again
      --testafter N     the host broadcasts N numbered test messages right after the transfer; every client must
                        dispatch the host's 0x72 before the first of them (per-sender order across a large message)
      --focus           bring the five windows to the foreground in turn while the transfer runs (procedure 4)
      --busy X          every machine ends the turn; the transfer starts when the host is idle again and X still
                        processes the turn (procedure 3; X runs a --slowai build)
  spike.py ordertest <n> <X> <Y>          X and Y each broadcast n numbered test messages at once; every other
                                          instance checks per-sender order (the delay comes from a --latency build)
  spike.py reset                          DONE on every instance (also from a stuck ARMED)
  spike.py auto [opts]                    automatic path: play turns as tools/turn5.py does until the game detects a
                                          heartbeat mismatch and transfers by itself (host PREPARE, ARM message,
                                          SEND), then the acceptance checks
      --host X          host instance (default A)
      --diverge X:S[:D] before the first turn add D (default 7) to the morale word +0x2dc of system S on X
      --diverge-host S[:D]  the same on the host
      --timeout S       give up when no transfer started within S seconds (default 600)
      --turns N         afterwards play N more turns and compare the checksum words after each
Field addresses come from <exe>.json of the build (default trek_t_spike.exe.json, env SPIKE_JSON); the game
instances are in test/A..E (env BOTF_TEST).
"""
import json, os, struct, sys, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import snapshot, compare, force_active, Dialogs, handle_dialogs
import spike_resync as S

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TEST = os.environ.get('BOTF_TEST') or next((d for d in (os.path.join(ROOT, 'test'), os.path.join(ROOT, '..', 'test'))
                                            if os.path.isdir(d)), os.path.join(ROOT, 'test'))
JSON = os.environ.get('SPIKE_JSON', os.path.join(ROOT, 'trek_t_spike.exe.json'))
F = json.load(open(JSON))['spike']
F = {k: int(v) for k, v in F.items()}
KIND = {S.K_PREP: 'PREP', S.K_SENT: 'SENT', S.K_QUEUED: 'QUEUED', S.K_REDISP: 'REDISP', S.K_RETIRE: 'RETIRE',
        S.K_RAW: 'RAW', S.K_APPLY: 'APPLY', S.K_FAIL: 'FAIL', S.K_DONE: 'DONE', S.K_TEST: 'TEST'}
FAIL = {S.F_RAWLEN: 'raw length', S.F_RAWCRC: 'raw crc', S.F_OVERFLOW: 'queue overflow', S.F_FLAG: 'load flag missing',
        S.F_FILE: 'host file missing', S.F_TOKEN: 'token not consumed', S.F_RETIRE: '0x89 record not retired'}
ST = H.load_state()
NAMES = [k for k in 'ABCDE' if k in ST and H.pid_alive(ST[k])]
P = {k: ST[k] for k in NAMES}


def rd(x, a, n):
    return H.readmem(P[x], a, n)


def u32(x, a):
    return struct.unpack('<I', rd(x, a, 4))[0]


def i32(x, a):
    return struct.unpack('<i', rd(x, a, 4))[0]


def f(x, name):
    return u32(x, F[name])


def setf(x, name, v):
    H.writemem(P[x], F[name], struct.pack('<I', v & 0xffffffff))


def rng_norm(x):
    r = bytearray(rd(x, 0x596bac, 0x120))
    r[4:0x18] = bytes(0x14)
    return zlib.crc32(bytes(r))


def players(x):
    t = rd(x, 0x5a29f8, 5 * 0x34)
    return [(struct.unpack_from('<I', t, i * 0x34 + 0x28)[0], t[i * 0x34 + 0x2c]) for i in range(5)]


def ident(x):
    """transport and session identity that must survive the transfer"""
    return {'own_id': u32(x, 0x5fd8c4), 'dplay': u32(x, 0x5fd97c) != 0, 'role': u32(x, 0x5fd978),
            'players': players(x), 'session': rd(x, 0x5a2928, 0x50).hex(), 'resumed_2994': u32(x, 0x5a2994)}


def rxpool(x):
    lp = u32(x, 0x5a0dfc)
    return i32(x, lp + 4) if lp else -1


def logs(x, since=0):
    n = f(x, 'log_n')
    out = []
    for k in range(max(since, n - S.LOG_N), n):
        e = rd(x, F['logring'] + (k % S.LOG_N) * 32, 32)
        out.append(struct.unpack('<8I', e))
    return out


def fmt(e):
    n, kind, a, b, c, d, e5, f6 = e
    name = KIND.get(kind, str(kind))
    if kind == S.K_APPLY:
        return ('%4d APPLY crc %08x %08x %04x rng %08x mask597504 %02x loaded %02x turn %d mask %02x'
                % (n, a, b, c & 0xffff, d, (c >> 16) & 0xff, c >> 24, e5, f6))
    if kind == S.K_FAIL:
        return '%4d FAIL %s (%x %x %x)' % (n, FAIL.get(a, a), b, c, d)
    if kind in (S.K_PREP, S.K_SENT):
        return '%4d %s len %d crc %08x mask %02x turn %d' % (n, name, a, b, c, d)
    if kind == S.K_RAW:
        return '%4d RAW len %d crc %08x expected %d %08x' % (n, a, b, c, d)
    return '%4d %s %x %x %x %x' % (n, name, a, b, c, d)


def owner_records(r):
    """a compare() line that differs only in system +0x80..+0xa7: the production records have an owner and a
    non-owner form between turns (outside every CRC); after a transfer each owner holds its turn-start form"""
    if not r.startswith('sys['):
        return False
    import re
    rng = [(int(a, 16), int(b, 16)) for a, b in re.findall(r'(0x[0-9a-f]+)-(0x[0-9a-f]+) a=', r)]
    return bool(rng) and all(0x80 <= a and b < 0xa8 for a, b in rng)


def status():
    for x in NAMES:
        print('%s state %d guard %d q %d result %d/%d fail %d applies %d queued %d redisp %d retired %d tokpass %d '
              'uifix %d incident %d/%d infobox %d snap %d/%d ownrest %d fallback %d turn %d busy %d crc %s rng %08x pool %d' % (
                  x, f(x, 'sp_state'), f(x, 'rs_guard'), f(x, 'q_count'), f(x, 'apply_result'), f(x, 'last_result'),
                  f(x, 'last_fail'), f(x, 'cnt_applies'), f(x, 'cnt_queued'), f(x, 'cnt_redispatch'),
                  f(x, 'cnt_retired'), f(x, 'cnt_tokpass'), f(x, 'cnt_uifix'), f(x, 'inc_open'), f(x, 'cnt_incident'), f(x, 'cnt_infobox'),
                  i32(x, F['snap_turn']), i32(x, F['ts_turn']), f(x, 'cnt_ownrestore'), f(x, 'prep_fallback'),
                  u32(x, 0x5a2918), i32(x, 0x5a291c),
                  rd(x, 0x597610, 10).hex(), rng_norm(x), rxpool(x)))


TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}


def end_turn(x):
    hw = H.main_window(P[x])
    H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.5)
    H.click(hw, *TURN[x], pid=P[x])


def wait(cond, timeout, what):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.25)
    print('TIMEOUT waiting for', what)
    return False


def diverge(x, si, dv, ref):
    a = u32(x, 0x5a36c8) + si * 0x328 + 0x2dc
    v = struct.unpack('<h', rd(x, a, 2))[0]
    H.writemem(P[x], a, struct.pack('<h', v + dv))
    d = compare(snapshot(P[ref]), snapshot(P[x]))
    print('diverged %s system %d morale %d -> %d; %s vs %s: %d diffs' % (x, si, v, v + dv, ref, x, len(d)))
    for r in d[:3]:
        print('   ', r[:160])


def run(argv):
    host = argv[argv.index('--host') + 1] if '--host' in argv else 'A'
    clients = [x for x in NAMES if x != host]
    badcrc = argv[argv.index('--badcrc') + 1] if '--badcrc' in argv else None
    res = {}
    assert all(f(x, 'sp_state') == 0 for x in NAMES), 'not all instances IDLE, use reset'
    before = {x: ident(x) for x in NAMES}
    pool0 = {x: rxpool(x) for x in NAMES}
    mark = {x: f(x, 'log_n') for x in NAMES}
    applies0 = {x: f(x, 'cnt_applies') for x in NAMES}
    for x in NAMES:
        setf(x, 'last_fail', 0)
    if '--endturn' in argv:
        x = argv[argv.index('--endturn') + 1]
        end_turn(x)
        if not wait(lambda: i32(x, 0x5a291c) == -1, 10, x + ' waiting'):
            return
        print(x, 'ended its turn, BUSY -1')
    if '--busy' in argv:
        x = argv[argv.index('--busy') + 1]
        t = u32(host, 0x5a2918)
        for y in NAMES:
            end_turn(y)
        if not wait(lambda: u32(host, 0x5a2918) > t and i32(host, 0x5a291c) == 0 and i32(x, 0x5a291c) == 1, 120,
                    'host idle while %s busy' % x):
            return
        print('host idle at turn %d, %s BUSY %d' % (u32(host, 0x5a2918), x, i32(x, 0x5a291c)))
    if '--diverge' in argv:
        spec = argv[argv.index('--diverge') + 1].split(':')
        diverge(spec[0], int(spec[1]), int(spec[2]) if len(spec) > 2 else 7, host)
    # 1 PREPARE (host)
    setf(host, 'sp_state', 1)
    if not wait(lambda: any(e[1] in (S.K_PREP, S.K_FAIL) for e in logs(host, mark[host])), 60, 'PREP on ' + host):
        return
    ln, crc = f(host, 'sp_len'), f(host, 'sp_crc')
    path = os.path.join(TEST, host, 'auto.sav')
    disk = open(path, 'rb').read()
    print('PREPARE %s: len %d crc %08x; on disk len %d crc %08x' % (host, ln, crc, len(disk), zlib.crc32(disk)))
    res['prepare matches the file'] = (ln, crc) == (len(disk), zlib.crc32(disk))
    if f(host, 'sp_state') != 1:
        print('host left PREPARE:', [fmt(e) for e in logs(host, mark[host])])
        return
    if '--nofile' in argv:
        os.replace(path, path + '.spike')
        print('renamed', path)
    inactive = argv[argv.index('--inactive') + 1].split(',') if '--inactive' in argv else []
    for x in inactive:
        H.writemem(P[x], 0x5a28d4, struct.pack('<i', 0))
    if inactive:
        print('inactive', inactive)
    # 2 ARMED (all): expected values into every client, then the state everywhere
    for x in clients:
        setf(x, 'sp_len', ln)
        setf(x, 'sp_crc', crc ^ (1 if x == badcrc else 0))
    for x in NAMES:
        setf(x, 'rs_guard', 1)
        setf(x, 'sp_state', 2)
    time.sleep(1)
    # 3 SEND (host); wake an inactive host first (the test build never waits, a release build would)
    H.user32.PostMessageW(H.main_window(P[host]), 0, 0, 0)
    t0 = time.time()
    stop_focus = []
    if '--focus' in argv:
        import threading

        def cycle():
            while not stop_focus:
                for x in NAMES:
                    H.user32.SetForegroundWindow(H.main_window(P[x]))
                    time.sleep(0.05)
        threading.Thread(target=cycle, daemon=True).start()
        time.sleep(0.3)
    setf(host, 'sp_state', 3)
    rx0 = {x: f(x, 'rx_n') for x in NAMES}
    if '--testafter' in argv:
        wait(lambda: f(host, 'sp_state') != 3, 60, 'SEND step')
        setf(host, 'test_n', int(argv[argv.index('--testafter') + 1]))
    host_failed = lambda: f(host, 'sp_state') == 0 and f(host, 'last_result') == 2
    ok = wait(lambda: all(f(x, 'sp_state') == 0 for x in NAMES) or host_failed(), 240, 'DONE on all')
    print('transfer %.1fs' % (time.time() - t0))
    stop_focus.append(1)
    if inactive:
        res['inactive windows still inactive'] = all(i32(x, 0x5a28d4) == 0 for x in inactive)
        for x in inactive:
            H.writemem(P[x], 0x5a28d4, struct.pack('<i', 1))
            H.user32.PostMessageW(H.main_window(P[x]), 0, 0, 0)
    if host_failed():
        time.sleep(2)
        print('host failed:', [fmt(e) for e in logs(host, mark[host])])
        res['host failure ends in DONE'] = True
        res['clients still ARMED, nothing queued'] = all(f(x, 'sp_state') == 2 and f(x, 'q_count') == 0 for x in clients)
        for x in clients:
            setf(x, 'sp_state', 5)
        res['clients reset to IDLE'] = wait(lambda: all(f(x, 'sp_state') == 0 for x in clients), 10, 'client reset')
        res['no apply anywhere'] = all(f(x, 'cnt_applies') == applies0[x] for x in NAMES)
        if os.path.exists(path + '.spike'):
            os.replace(path + '.spike', path)
        print('ACCEPTANCE')
        for k, v in res.items():
            print('  %-40s %s' % (k, 'ok' if v else 'FAIL'))
        return
    if '--nofile' in argv and os.path.exists(path + '.spike'):
        os.replace(path + '.spike', path)
    if not ok:
        status()
        return
    time.sleep(2)
    # evidence
    applies = {}
    for x in NAMES:
        print('--', x, 'result', f(x, 'last_result'))
        for e in logs(x, mark[x]):
            print('   ', fmt(e))
            if e[1] == S.K_APPLY:
                applies[x] = e
    after = {x: ident(x) for x in NAMES}
    for x in NAMES:
        if before[x] != after[x]:
            print('IDENTITY CHANGED on', x, {k: (before[x][k], after[x][k]) for k in before[x] if before[x][k] != after[x][k]})
    res['ids and session unchanged'] = before == after and all(after[x]['dplay'] for x in NAMES)
    expect = [x for x in NAMES if x != badcrc]
    res['one apply per machine'] = all(f(x, 'cnt_applies') - applies0[x] == (1 if x in expect else 0) for x in NAMES)
    res['applied where expected'] = sorted(applies) == sorted(expect)
    if applies:
        res['mask 597504 == loaded mask'] = all(((e[4] >> 16) & 0xff) == (e[4] >> 24) for e in applies.values())
        vals = {x: (e[2], e[3], e[4] & 0xffff, e[5]) for x, e in applies.items()}
        res['CRC words and RNG equal (apply log)'] = len(set(vals.values())) == 1
    now = {x: (rd(x, 0x597610, 10), rng_norm(x)) for x in expect}
    res['CRC words and RNG equal (now)'] = len(set(now.values())) == 1
    if '--testafter' in argv:
        time.sleep(3)
        hid = u32(host, 0x5fd8c4)
        for x in clients:
            seq = [struct.unpack('<III', rd(x, F['rxring'] + (k % S.RX_N) * 12, 12)) for k in range(rx0[x], f(x, 'rx_n'))]
            seq = [t for w, l, t in seq if w == hid]
            first72 = seq.index(0x72) if 0x72 in seq else None
            firsttest = seq.index(S.TEST_MSG) if S.TEST_MSG in seq else None
            print('  %s: host messages in dispatch order %s' % (x, ' '.join('%x' % t for t in seq[:12])))
            res['%s: 0x72 before the test messages' % x] = first72 is not None and firsttest is not None and first72 < firsttest
    res['queue empty, token clear'] = all(f(x, 'q_count') == 0 and f(x, 'tok_valid') == 0 for x in NAMES)
    pool1 = {x: rxpool(x) for x in NAMES}
    print('rx pool before', pool0, 'after', pool1)
    res['rx pool not grown'] = all(pool1[x] <= pool0[x] for x in NAMES)
    if badcrc:
        res['rejected on ' + badcrc] = f(badcrc, 'last_fail') == S.F_RAWCRC and f(badcrc, 'last_result') == 2
        res['dialog closed on ' + badcrc] = u32(badcrc, 0x597508) == 0
    if '--keep' not in argv:
        s0 = snapshot(P[host])
        for x in clients:
            d = compare(s0, snapshot(P[x]))
            own = [r for r in d if owner_records(r)]
            d = [r for r in d if not owner_records(r)]
            print('  %s vs %s: %d diffs (+ %d systems differing only in production records +0x80..+0xa7)' % (host, x, len(d), len(own)))
            for r in d[:4]:
                print('     ', r[:200])
            res['state %s == host' % x] = (len(d) == 0) != (x == badcrc and '--diverge' in argv)
    print('ACCEPTANCE')
    for k, v in res.items():
        print('  %-40s %s' % (k, 'ok' if v else 'FAIL'))


AUTO = ('sp_detect', 'sp_detect_tick', 'sp_quiet', 'sp_epoch', 'sp_arm_rx', 'sp_auto_n', 'sp_fallback')
SETTLE = 4                      # s idle at the new turn before the next TURN: the 0x71 compare runs right after the turn


def counters():
    return {x: {k: f(x, k) for k in AUTO + ('cnt_applies', 'log_n')} for x in NAMES}


def spike_idle(x):
    return f(x, 'sp_state') == 0 and f(x, 'rs_guard') == 0


def detected(c):
    """instances that detected a heartbeat mismatch since the counters c"""
    return [x for x in NAMES if f(x, 'sp_detect_tick') != c[x]['sp_detect_tick'] or f(x, 'sp_detect') and not c[x]['sp_detect']]


def checksums():
    v = {x: '%s/%08x' % (rd(x, 0x597610, 10).hex(), rng_norm(x)) for x in NAMES}
    return 'checksum words equal' if len(set(v.values())) == 1 else 'checksum words DIFFER %s' % v


def stock_box(x):
    """the stock mismatch box FUN_005004a4 on the main thread's stack: return 0x5100e9 (post-turn compare) or 0x51033f
    (incoming 0x71 compare), as tools/rngtimeline.py"""
    import ctypes
    from dbg import WOW64_CONTEXT, k32, rpm
    from sampler import threads
    hp = k32.OpenProcess(0x1F0FFF, False, P[x]); th = k32.OpenThread(0x1F03FF, False, threads(P[x])[0])
    try:
        k32.SuspendThread(th)
        ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
        k32.Wow64GetThreadContext(th, ctypes.byref(ctx)); stk = rpm(hp, ctx.Esp, 0x2000)
    finally:
        k32.ResumeThread(th); k32.CloseHandle(th); k32.CloseHandle(hp)
    return any(struct.unpack_from('<I', stk, o)[0] in (0x5100e9, 0x51033f) for o in range(0, len(stk) - 3, 4))


def press(x, t, dlg, stop):
    """tools/turn5.py: F1, known dialogs, TURN until x is busy or past turn t; no more input once stop() is true"""
    hw = H.main_window(P[x])
    done = lambda: stop() or i32(x, 0x5a291c) != 0 or u32(x, 0x5a2918) > t
    for _ in range(8):
        if done():
            return True
        H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
        time.sleep(0.5)
        handle_dialogs(dlg, x, P[x], print)
        H.click(hw, *TURN[x], pid=P[x])
        for _ in range(10):
            time.sleep(0.3)
            if done():
                return True
    return False


def play_turn(host, dlg, c, timeout=300):
    """one turn on every instance; returns (turn, outcome): 'turn' once every game is idle at the next turn for SETTLE s
    without a detection, 'transfer' as soon as the host started one (or any machine left IDLE), else what went wrong"""
    t = u32(host, 0x5a2918)
    moving = lambda: f(host, 'sp_auto_n') != c[host]['sp_auto_n'] or not all(spike_idle(y) for y in NAMES)
    force_active(P)
    for x in NAMES:
        if not press(x, t, dlg, moving):
            return t, 'TURN press failed on ' + x
    t0 = tdlg = time.time(); calm = None
    while time.time() - t0 < timeout:
        if moving():
            return t, 'transfer'
        fb = [y for y in NAMES if f(y, 'sp_fallback') != c[y]['sp_fallback']]
        if fb:
            return t, 'fallback (stock error) on %s' % fb
        force_active(P)
        if all(u32(y, 0x5a2918) > t and i32(y, 0x5a291c) == 0 for y in NAMES):
            calm = calm or time.time()
            if time.time() - calm > SETTLE:
                det, hb = detected(c), checksums() != 'checksum words equal'
                box = [y for y in NAMES if stock_box(y)]
                if box:
                    return t, 'stock error box on %s' % box
                if not det and not hb:
                    return t, 'turn'
                if time.time() - calm > SETTLE + 60:        # a detection must start the transfer within a minute
                    q = max(f(y, 'sp_quiet') for y in NAMES)
                    return t, ('mismatch detected on %s, no transfer started' % det if det else
                               '%s, no mismatch detected%s' % (checksums(), ' (quiet up to turn %d)' % q
                                                                if u32(host, 0x5a2918) <= q else ''))
        else:
            calm = None
            if time.time() - tdlg > 5:
                for y in NAMES:
                    handle_dialogs(dlg, y, P[y], print)
                tdlg = time.time()
        time.sleep(0.25)
    return t, 'timeout, turn/busy %s' % {y: (u32(y, 0x5a2918), i32(y, 0x5a291c)) for y in NAMES}


def wait_transfer(host, c, timeout=240):
    """until every machine is IDLE and the host failed or every client applied, failed or fell back; returns
    (ok, stock boxes seen)"""
    failed = lambda x: any(e[1] == S.K_FAIL for e in logs(x, c[x]['log_n']))
    over = lambda x: f(x, 'cnt_applies') != c[x]['cnt_applies'] or f(x, 'sp_fallback') != c[x]['sp_fallback'] or failed(x)
    t0 = tbox = time.time(); boxes = set()
    while time.time() - t0 < timeout:
        if all(spike_idle(x) for x in NAMES) and (failed(host) or all(over(x) for x in NAMES if x != host)):
            return True, boxes
        if time.time() - tbox > 2:
            boxes |= {x for x in NAMES if stock_box(x)}; tbox = time.time()
        time.sleep(0.25)
    print('TIMEOUT waiting for the end of the transfer')
    return False, boxes


def auto(argv):
    miss = [k for k in AUTO if k not in F]
    if miss:
        print('%s has no field %s: not a build with the automatic resync (build it with build_test.py --fix --spike '
              'and the current spike_resync.py, SPIKE_JSON=<that exe>.json)' % (JSON, ', '.join(miss)))
        return
    host = argv[argv.index('--host') + 1] if '--host' in argv else 'A'
    clients = [x for x in NAMES if x != host]
    timeout = float(argv[argv.index('--timeout') + 1]) if '--timeout' in argv else 600
    more = int(argv[argv.index('--turns') + 1]) if '--turns' in argv else 0
    assert all(spike_idle(x) for x in NAMES), 'not all instances IDLE, use reset'
    c = counters()
    before = {x: ident(x) for x in NAMES}
    for x in NAMES:
        setf(x, 'last_fail', 0)
    if '--diverge' in argv:
        spec = argv[argv.index('--diverge') + 1].split(':')
        diverge(spec[0], int(spec[1]), int(spec[2]) if len(spec) > 2 else 7, host if spec[0] != host else clients[0])
    if '--diverge-host' in argv:
        spec = argv[argv.index('--diverge-host') + 1].split(':')
        diverge(host, int(spec[0]), int(spec[1]) if len(spec) > 1 else 7, clients[0])
    dlg = Dialogs()
    t0 = time.time()
    while True:
        pool0 = {x: rxpool(x) for x in NAMES}
        t, how = play_turn(host, dlg, c)
        if how != 'turn':
            break
        print('turn %d -> %d: no mismatch, %s' % (t, u32(host, 0x5a2918), checksums()))
        if time.time() - t0 > timeout:
            print('TIMEOUT: no automatic transfer within %.0fs' % (time.time() - t0))
            status()
            return
    if how != 'transfer':
        print('turn %d:' % t, how)
        status()
        return
    det = detected(c)
    print('turn %d -> %d: transfer started by %s (sp_auto_n %d -> %d), mismatch detected on %s' % (
        t, u32(host, 0x5a2918), host, c[host]['sp_auto_n'], f(host, 'sp_auto_n'), det))
    ts = time.time()
    ok, boxes = wait_transfer(host, c)
    print('transfer %.1fs' % (time.time() - ts))
    time.sleep(2)
    applies = {}
    for x in NAMES:
        print('--', x, 'result', f(x, 'last_result'))
        for e in logs(x, c[x]['log_n']):
            print('   ', fmt(e))
            if e[1] == S.K_APPLY:
                applies[x] = e
    if not ok:
        status()
        return
    d = lambda x, k: f(x, k) - c[x][k]
    det = sorted(set(det) | set(detected(c)))
    for x in NAMES:
        print('%s detect %d tick %d quiet %d epoch %d arm_rx +%d auto_n +%d applies +%d fallback +%d' % (
            x, f(x, 'sp_detect'), f(x, 'sp_detect_tick'), f(x, 'sp_quiet'), f(x, 'sp_epoch'), d(x, 'sp_arm_rx'),
            d(x, 'sp_auto_n'), d(x, 'cnt_applies'), d(x, 'sp_fallback')))
    res = {}
    res['mismatch detected on the host'] = host in det
    res['one start, by the host (sp_auto_n)'] = d(host, 'sp_auto_n') == 1 and all(d(x, 'sp_auto_n') == 0 for x in clients)
    res['ARM received on every client'] = all(d(x, 'sp_arm_rx') >= 1 for x in clients)
    after = {x: ident(x) for x in NAMES}
    for x in NAMES:
        if before[x] != after[x]:
            print('IDENTITY CHANGED on', x, {k: (before[x][k], after[x][k]) for k in before[x] if before[x][k] != after[x][k]})
    res['ids and session unchanged'] = before == after and all(after[x]['dplay'] for x in NAMES)
    res['one apply per client'] = all(d(x, 'cnt_applies') == 1 for x in clients)
    res['applied on every client'] = all(x in applies for x in clients)
    if applies:
        res['mask 597504 == loaded mask'] = all(((e[4] >> 16) & 0xff) == (e[4] >> 24) for e in applies.values())
        vals = {x: (e[2], e[3], e[4] & 0xffff, e[5]) for x, e in applies.items()}
        res['CRC words and RNG equal (apply log)'] = len(set(vals.values())) == 1
    res['CRC words and RNG equal (now)'] = checksums() == 'checksum words equal'
    res['no fallback (sp_fallback)'] = all(d(x, 'sp_fallback') == 0 for x in NAMES)
    boxes |= {x for x in NAMES if stock_box(x)}
    if boxes:
        print('stock error box on', sorted(boxes))
    res['no stock error box'] = not boxes
    res['queue empty, token clear'] = all(f(x, 'q_count') == 0 and f(x, 'tok_valid') == 0 for x in NAMES)
    print('rx pool before the transfer turn', pool0, 'after', {x: rxpool(x) for x in NAMES})
    s0 = snapshot(P[host])
    for x in clients:
        r = compare(s0, snapshot(P[x]))
        own = [l for l in r if owner_records(l)]
        r = [l for l in r if not owner_records(l)]
        print('  %s vs %s: %d diffs (+ %d systems differing only in production records +0x80..+0xa7)' % (host, x, len(r), len(own)))
        for l in r[:4]:
            print('     ', l[:200])
        res['state %s == host' % x] = len(r) == 0
    print('ACCEPTANCE')
    for k, v in res.items():
        print('  %-40s %s' % (k, 'ok' if v else 'FAIL'))
    if not more:
        return
    print('-- %d more turns' % more)
    eq = 0
    for k in range(more):
        c = counters()
        t, how = play_turn(host, dlg, c)
        note = ''
        if how == 'transfer':
            ok, boxes = wait_transfer(host, c)
            time.sleep(2)
            note = ', TRANSFER again (sp_auto_n +%d, detected on %s, %s)' % (
                f(host, 'sp_auto_n') - c[host]['sp_auto_n'], detected(c), 'finished' if ok else 'NOT FINISHED')
            if not ok or boxes:
                print('turn %d%s%s' % (t, note, ', stock error box on %s' % sorted(boxes) if boxes else ''))
                status()
                break
        elif how != 'turn':
            print('turn %d: %s' % (t, how))
            status()
            break
        cs = checksums()
        eq += cs == 'checksum words equal'
        s0 = snapshot(P[host])
        diffs = {x: len([r for r in compare(s0, snapshot(P[x])) if not owner_records(r)]) for x in clients}
        print('turn %d -> %d: %s, state diffs vs %s %s%s' % (t, u32(host, 0x5a2918), cs, host, diffs, note))
    print('checksum words equal after %d of %d more turns' % (eq, more))


def ordertest(n, xs):
    marks = {x: f(x, 'trx_n') for x in NAMES}
    ids = {x: u32(x, 0x5fd8c4) for x in NAMES}
    seq0 = {x: f(x, 'test_seq') for x in xs}
    for x in xs:
        setf(x, 'test_n', n)
    time.sleep(3 + n * 0.05)
    allok = True
    for r in NAMES:
        got = {}
        for k in range(marks[r], f(r, 'trx_n')):
            w, sq = struct.unpack('<II', rd(r, F['trxring'] + (k % S.TRX_N) * 8, 8))
            got.setdefault(w, []).append(sq)
        for x in xs:
            if x == r:
                continue
            exp = list(range(seq0[x], seq0[x] + n))
            s = got.get(ids[x], [])
            ok = s == exp
            allok &= ok
            print('%s from %s (id %08x): %d messages, %s' % (r, x, ids[x], len(s), 'in order' if ok else 'ORDER/LOSS %s' % s[:20]))
        inter = [w for k in range(marks[r], f(r, 'trx_n'))
                 for w in [struct.unpack('<I', rd(r, F['trxring'] + (k % S.TRX_N) * 8, 4))[0]]]
        switches = sum(1 for i in range(1, len(inter)) if inter[i] != inter[i - 1])
        print('   %s: senders interleaved %d times' % (r, switches))
    print('ORDER', 'ok' if allok else 'FAIL')


def rx(x, n):
    tab = {pid: (i, emp) for i, (pid, emp) in enumerate(players(x))}
    tot = f(x, 'rx_n')
    last = {}
    for k in range(max(0, tot - n), tot):
        w, l, t = struct.unpack('<III', rd(x, F['rxring'] + (k % S.RX_N) * 12, 12))
        slot = tab.get(w)
        mono = '' if w not in last or l > last[w] else ('  repeat (re-dispatch)' if l == last[w] else '  NOT INCREASING')
        if l != last.get(w):
            last[w] = l
        print('%5d type %#06x wParam %08x lParam %6d  %s%s' % (k, t, w, l, 'player %d empire %d' % slot if slot else 'NOT IN TABLE', mono))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'status':
        status()
    elif cmd == 'log':
        for x in sys.argv[2:] or NAMES:
            print('--', x)
            for e in logs(x):
                print('   ', fmt(e))
    elif cmd == 'rx':
        rx(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 40)
    elif cmd == 'run':
        run(sys.argv[2:])
    elif cmd == 'auto':
        auto(sys.argv[2:])
    elif cmd == 'ordertest':
        ordertest(int(sys.argv[2]), sys.argv[3:5])
    elif cmd == 'reset':
        for x in NAMES:
            setf(x, 'sp_state', 5)
        time.sleep(1)
        status()
