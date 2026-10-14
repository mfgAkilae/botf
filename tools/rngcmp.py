"""Compare RNG call sequences of A and B for one turn and print the first divergence with context.
usage: rngcmp.py <turn>"""
import os, re, sys
TL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'turnlog')

def load(path):
    ev = []; lines = open(path).read().splitlines()
    for i, l in enumerate(lines):
        m = re.match(r'\s*([\d.]+) tid=\s*\d+ (\S+)\s+eax=(\w+) ebx=(\w+) ecx=(\w+) edx=(\w+)', l)
        if m and i + 1 < len(lines) and 'stack:' in lines[i + 1]:
            st = lines[i + 1].split('stack:')[1].split()
            busy = lines[i + 1].split('busy=')[1].split()[0]
            ev.append(dict(t=float(m.group(1)), fn=m.group(2), eax=m.group(3), edx=m.group(6), busy=busy, st=st))
    return ev

t = int(sys.argv[1])
a = load(os.path.join(TL, 'rng_t%03d_A.log' % t)); b = load(os.path.join(TL, 'rng_t%03d_B.log' % t))
print('calls A', len(a), 'B', len(b))
key = lambda e: (e['fn'], e['eax'], e['edx'], tuple(e['st'][:3]))
for i in range(max(len(a), len(b))):
    ea = a[i] if i < len(a) else None; eb = b[i] if i < len(b) else None
    if ea is None or eb is None or key(ea) != key(eb):
        print('first divergence at call', i)
        for j in range(max(0, i - 3), min(i + 4, max(len(a), len(b)))):
            for n, s in (('A', a), ('B', b)):
                if j < len(s):
                    e = s[j]; print('  %s[%d] %s eax=%s edx=%s busy=%s stack %s' % (n, j, e['fn'], e['eax'], e['edx'], e['busy'], ' '.join(e['st'])))
        break
else:
    print('identical')
