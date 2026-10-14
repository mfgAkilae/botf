"""M1 demonstration: a kill request that turn processing created on A (type 9, payload = target seqno S)
meets, on B, a different live order that carries the same number S (as happens when the per-machine
sequence counters have drifted). B executes the request at the next turn start and kills that order.
Steps: play turns until A holds a processing kill request (original exe) or N turns passed (fixed exe),
then give one of B's AI task-force/production orders the number S and play on.
usage: m1demo.py <max_turns_to_find> <turns_after>"""
import os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, snapshot, compare
HERE = os.path.dirname(os.path.abspath(__file__))
st = H.load_state(); P = {'A': st['A'], 'B': st['B']}
u = lambda n, a: struct.unpack('<I', H.readmem(P[n], a, 4))[0]

def orders(n):
    out = []; node = u(n, u(n, 0x59024c))
    while node:
        h = H.readmem(P[n], node + 8, 0x18)
        sq, gen, emp = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]; bp = struct.unpack_from('<I', h, 0x14)[0]
        out.append(dict(node=node, seq=sq, gen=gen, emp=emp, type=ty, body=bp)); node = u(n, node)
    return out

def play(k):
    for _ in range(k):
        r = subprocess.run([sys.executable, '-I', '-u', os.path.join(HERE, 'autoturn.py'), '1'], capture_output=True, text=True).stdout
        line = [l for l in r.splitlines() if l.startswith('turn')]
        rep = compare(snapshot(P['A']), snapshot(P['B']))
        print(line[-1] if line else 'no result', '| state diffs', len(rep)); sys.stdout.flush()
        for x in rep[:8]: print('   ', x)
        if rep: return True
    return False

local = {n: H.readmem(P[n], 0x5a2b2a, 1)[0] for n in 'AB'}
S = None; creator = None
for i in range(int(sys.argv[1])):
    for n in 'AB':
        req = [o for o in orders(n) if o['type'] == 9 and o['emp'] == local[n]]
        if req:
            S = u(n, req[0]['body']); creator = n
            print('%s holds a kill request from turn processing, target seqno %#x' % (n, S)); break
    if S is not None: break
    if play(1): sys.exit(1)
if S is None:
    # fixed exe: no processing requests; use the number of a minor-race order as the collision value
    S = max(o['seq'] for o in orders('A') if o['seq'] >= 0xd5555552)
    print('no kill request found on A within the window; using seqno %#x of a live minor order' % S)
recv = 'B' if creator != 'B' else 'A'
cand = [o for o in orders(recv) if o['emp'] in (1, 2, 4) and o['type'] in (0, 2)]
victim = cand[0]
print('%s: renaming AI order seq %#x (emp %d type %d gen %d) to %#x' % (recv, victim['seq'], victim['emp'], victim['type'], victim['gen'], S))
# rename the same logical order on both machines, so only the kill request can make them differ
for n in 'AB':
    same = [o for o in orders(n) if o['seq'] == victim['seq'] and o['emp'] == victim['emp']]
    if same:
        H.writemem(P[n], same[0]['node'] + 8, struct.pack('<I', S)); print('%s: order renamed' % n)
print('desync' if play(int(sys.argv[2])) else 'no state difference')
