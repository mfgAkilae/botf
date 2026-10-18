"""Monster-heavy test: every <interval> turns, between two turns (all games idle on the same turn), set the random-monster
countdown [0x58fdb0] to 0 on every game, so the next turn calculation spawns a monster (FUN_0044cbe0 -> FUN_0044b220).
The write is the same on every machine at the same point of the game. Stops when <logdir>/stop exists.
usage: monsterpoke.py <logdir> [interval]"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32

D = sys.argv[1]; IV = int(sys.argv[2]) if len(sys.argv) > 2 else 3
st = H.load_state(); P = {x: st[x] for x in 'ABCDE' if H.pid_alive(st[x])}
log = open(os.path.join(D, 'monsterpoke.log'), 'a')
done = set()
while not os.path.exists(os.path.join(D, 'stop')):
    P = {x: p for x, p in P.items() if H.pid_alive(p)}
    try:
        turns = {x: u32(p, 0x5a2918) for x, p in P.items()}
        busy = {x: i32(p, 0x5a291c) for x, p in P.items()}
    except OSError:
        time.sleep(2); continue
    t = min(turns.values()) if turns else 0
    if len(set(turns.values())) == 1 and all(b == 0 for b in busy.values()) and t % IV == 0 and t not in done:
        time.sleep(1)
        if all(i32(p, 0x5a291c) == 0 and u32(p, 0x5a2918) == t for p in P.values()):
            before = {x: i32(p, 0x58fdb0) for x, p in P.items()}
            for p in P.values():
                H.writemem(p, 0x58fdb0, struct.pack('<i', 0))
            done.add(t)
            log.write('%s turn %d: countdown %s -> 0\n' % (time.strftime('%H:%M:%S'), t, before)); log.flush()
    time.sleep(1)
