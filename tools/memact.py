"""Find memory changed by a UI action on one instance, excluding background noise.
usage: memact.py <inst> <uirng actions...>"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from memsnap import snap

inst = sys.argv[1]; pid = H.load_state()[inst]
here = os.path.dirname(os.path.abspath(__file__))
s0 = snap(pid); time.sleep(2.5); s1 = snap(pid)
noise = set()
for base, b in s1.items():
    o = s0.get(base)
    if o is None or len(o) != len(b):
        continue
    if o != b:
        for i in range(len(b)):
            if b[i] != o[i]:
                noise.add(base + i)
subprocess.run([sys.executable, '-I', os.path.join(here, 'uirng.py'), inst] + sys.argv[2:], capture_output=True)
s2 = snap(pid)
runs = []
for base, b in sorted(s2.items()):
    o = s1.get(base)
    if o is None or len(o) != len(b) or o == b:
        continue
    i = 0
    while i < len(b):
        if b[i] != o[i] and base + i not in noise:
            j = i
            while j < len(b) and b[j] != o[j]:
                j += 1
            runs.append((base + i, o[i:j], b[i:j])); i = j
        else:
            i += 1
print('noise bytes', len(noise), 'changed runs', len(runs))
import collections
byreg = collections.defaultdict(list)
for r in runs:
    if r[0] < 0x400000:
        continue
    byreg[r[0] & ~0xffff].append(r)
for reg, rs in sorted(byreg.items()):
    tot = sum(len(x[2]) for x in rs)
    print('region %08x runs %d bytes %d' % (reg, len(rs), tot))
    if len(rs) <= 40 and tot < 2000:
        for a, o, n in rs:
            print('   %08x +%-4d old %s new %s' % (a, len(n), o[:24].hex(), n[:24].hex()))
