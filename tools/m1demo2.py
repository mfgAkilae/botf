"""A/B demonstration of the kill-request collision (identical procedure for original and fixed exe).
1. play turns with kill tracing until turn processing (FUN_00466468, return address 0x4665d6) kills an
   order with number S on both machines (that is the moment the original also queues a kill request);
2. give one AI order the number S on BOTH machines (what drifting counters produce in long games);
3. play two more turns and compare: the original forwards the request and the receiver kills the
   AI order, the fixed exe sends no request.
usage: m1demo2.py <max_turns>"""
import os, re, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, snapshot, compare
HERE = os.path.dirname(os.path.abspath(__file__)); TL = os.path.join(HERE, '..', 'turnlog')
st = H.load_state(); P = {'A': st['A'], 'B': st['B']}
u = lambda n, a: struct.unpack('<I', H.readmem(P[n], a, 4))[0]

def orders(n):
    out = []; node = u(n, u(n, 0x59024c))
    while node:
        h = H.readmem(P[n], node + 8, 0x18)
        sq, gen, emp = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]
        out.append(dict(node=node, seq=sq, gen=gen, emp=emp, type=ty)); node = u(n, node)
    return out

def turn(trace=True):
    t = u32(P['A'], 0x5a2918); stopf = os.path.join(TL, 'm1.stop')
    if trace:
        if os.path.exists(stopf): os.remove(stopf)
        env = dict(os.environ, TRACER_STOP=stopf, ONLY2='0')
        for n in 'AB':
            subprocess.Popen([sys.executable, '-I', '-u', os.path.join(HERE, 'ktrace.py'), str(P[n]), '900'],
                             stdout=open(os.path.join(TL, 'm1_%s.log' % n), 'w'), stderr=subprocess.STDOUT, env=env)
        time.sleep(2.5)
    r = subprocess.run([sys.executable, '-I', '-u', os.path.join(HERE, 'autoturn.py'), '1'], capture_output=True, text=True).stdout
    if trace:
        open(stopf, 'w').close(); time.sleep(3)
    rep = compare(snapshot(P['A']), snapshot(P['B']))
    line = [l for l in r.splitlines() if l.startswith('turn')]
    print('turn %d: %s | state diffs %d' % (t, line[-1] if line else 'no result', len(rep))); sys.stdout.flush()
    for x in rep[:8]: print('   ', x)
    return rep

S = None
for i in range(int(sys.argv[1])):
    if turn(): print('desync before the experiment'); sys.exit(1)
    txt = open(os.path.join(TL, 'm1_A.log')).read().splitlines()
    for j, l in enumerate(txt):
        if 'KILL mode 0' in l and 'stack 4665d6' in l and j + 1 < len(txt):
            m = re.search(r'matched order seq=(\d+) gen=(\d+) emp=(\d+) type=(-?\d+)', txt[j + 1])
            if m:
                cand_s = int(m.group(1))
                local_a = H.readmem(P['A'], 0x5a2b2a, 1)[0]
                reqs = [o for o in orders('A') if o['type'] == 9 and o['emp'] == local_a]
                req_targets = [u('A', u('A', o['node'] + 8 + 0x14)) for o in reqs]
                if '--need-request' in sys.argv and cand_s not in req_targets:
                    continue
                if '--same-range' in sys.argv and (cand_s < 0xd5555552 or not [o for o in orders('B') if o['seq'] >= 0xd5555552 and o['seq'] != cand_s and o['emp'] >= 5]):
                    continue
                S = cand_s
                print('turn processing killed order seq %#x (emp %s type %s) on A; kill requests queued on A for: %s'
                      % (S, m.group(3), m.group(4), [hex(x) for x in req_targets])); break
    if S is not None: break
if S is None: print('no processing kill seen'); sys.exit(3)
if '--same-range' in sys.argv:
    # victim from the same number range as the target: another live order of a minor race
    # (all minor races share one counter), which is what drifting counters make collide
    ob = [o for o in orders('B') if o['seq'] >= 0xd5555552 and o['seq'] != S and o['emp'] >= 5]
else:
    ob = sorted([o for o in orders('B') if o['emp'] in (1, 2, 4) and o['type'] in (0, 2)], key=lambda o: o['type'] != 2)
if not ob: print('no victim candidate'); sys.exit(3)
victim = ob[0]
# drift: the same logical order carries a different number on B than on A
H.writemem(P['B'], victim['node'] + 8, struct.pack('<I', S))
print('order (emp %d type %d gen %d) renamed %#x -> %#x on B only (counter drift)' % (victim['emp'], victim['type'], victim['gen'], victim['seq'], S))
rep = turn() or turn() or turn()
for n in 'AB':
    print(n, 'kill requests executed:', [l.strip() for l in open(os.path.join(TL, 'm1_%s.log' % n)) if 'KILL mode 2' in l or 'kill-request' in l or 'matched' in l and 'mode 2' in l][:6])
print('RESULT:', 'DESYNC' if rep else 'in sync')
