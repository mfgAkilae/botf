"""Mid-processing race test.
Setup: A = normal exe, B = exe made slow before _turnResolveEconomyPhase2 (--slowphase).
1. B and A end turn N (A last). A finishes quickly, B is still processing N (sleeping).
2. While B is busy, A changes Cardassia's build queue (fusion plant) and ends turn N+1
   -> A sends 0x74/0x68 for N+1 while B is still inside N.
3. When B has finished N, compare Cardassia's current production on both machines.
usage: race_test.py
"""
import os, struct, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, snapshot, compare

st = H.load_state()
P = {'A': st['A'], 'B': st['B']}


def press(name, t):
    pid = P[name]
    for _ in range(4):
        if i32(pid, BUSY_ADDR) != 0 or u32(pid, TURN_ADDR) > t:
            return True
        H.click(H.main_window(pid), *TURN_BTN[name], pid=pid)
        for _ in range(10):
            time.sleep(0.3)
            if i32(pid, BUSY_ADDR) != 0 or u32(pid, TURN_ADDR) > t:
                return True
    return False


def cardassia():
    pid = P['A']
    sp = u32(pid, 0x5a36c8)
    cnt = struct.unpack('<H', H.readmem(pid, 0x5a36bc, 2))[0]
    for i in range(cnt):
        s = H.readmem(pid, sp + i * 0x328, 0x60)
        if s[8:0x30].split(b'\0')[0] == b'Cardassia':
            return i
    raise SystemExit('Cardassia not found')


def cur(name, idx):
    pid = P[name]
    sp = u32(pid, 0x5a36c8)
    s = H.readmem(pid, sp + idx * 0x328, 0x328)
    order, inv, unrest, build = struct.unpack_from('<ihhh', s, 0x80)
    qp = struct.unpack_from('<I', s, 0xa8)[0]
    q = H.readmem(pid, qp, 0x6c)
    return 'cur(order=%d inv=%d build=%d) q0(order=%d build=%d)' % (order, inv, build, struct.unpack_from('<i', q, 0)[0], struct.unpack_from('<h', q, 8)[0])



def main():
    idx = cardassia()
    t = u32(P['A'], TURN_ADDR)
    print('turn', t, 'Cardassia idx', idx)
    print('before  A', cur('A', idx), '| B', cur('B', idx))
    assert press('B', t) and press('A', t)
    t0 = time.time()
    while not (u32(P['A'], TURN_ADDR) > t and i32(P['A'], BUSY_ADDR) == 0):
        time.sleep(0.2)
        if time.time() - t0 > 120:
            raise SystemExit('A did not finish')
    print('A finished turn %d after %.1fs; B busy=%d turn=%d' % (t, time.time() - t0, i32(P['B'], BUSY_ADDR), u32(P['B'], TURN_ADDR)))
    # A, now in turn t+1, edits the queue and ends the turn right away
    subprocess.check_call([sys.executable, '-I', os.path.join(os.path.dirname(__file__), 'queue.py'), 'A', 'fusion', str(idx)])
    assert press('A', t + 1)
    print('A ended turn %d at %.1fs (B busy=%d)' % (t + 1, time.time() - t0, i32(P['B'], BUSY_ADDR)))
    while not (u32(P['B'], TURN_ADDR) > t and i32(P['B'], BUSY_ADDR) == 0):
        time.sleep(0.2)
        if time.time() - t0 > 180:
            raise SystemExit('B did not finish')
    time.sleep(1)
    print('B finished turn %d after %.1fs' % (t, time.time() - t0))
    print('after   A', cur('A', idx), '| B', cur('B', idx))
    rep = compare(snapshot(P['A']), snapshot(P['B']))
    print('state diffs after turn %d:' % t, len(rep))
    for x in rep[:10]:
        print('   ', x)


if __name__ == '__main__':
    main()
