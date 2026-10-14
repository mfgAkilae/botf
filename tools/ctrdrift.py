"""Which UI actions consume order sequence numbers? Prints counter deltas on one instance per action.
usage: ctrdrift.py <inst> <uirng actions...>"""
import os, struct, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
inst = sys.argv[1]; pid = H.load_state()[inst]
here = os.path.dirname(os.path.abspath(__file__))
ctr = lambda: struct.unpack('<6I', H.readmem(pid, 0x590230, 24))
for a in sys.argv[2:]:
    c0 = ctr()
    subprocess.run([sys.executable, '-I', os.path.join(here, 'uirng.py'), inst, a], capture_output=True)
    c1 = ctr()
    print('%-14s emp0..4,minor: %s' % (a, ' '.join('%+d' % ((y - x) & 0xffffffff if (y - x) & 0xffffffff < 0x80000000 else (y - x) - (1 << 32)) for x, y in zip(c0, c1))))
