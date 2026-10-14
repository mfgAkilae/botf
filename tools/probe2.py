"""B ends the turn first, then A performs UI actions (uirng syntax), then A ends the turn; report diffs.
usage: probe2.py <label> <actions...>"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, snapshot, compare, force_active
from race_test import press
here = os.path.dirname(os.path.abspath(__file__))
st = H.load_state(); P = {'A': st['A'], 'B': st['B']}
print('==', sys.argv[1])
force_active(P)
t = u32(P['A'], TURN_ADDR)
assert press('B', t), 'B press failed'
if len(sys.argv) > 2:
    out = subprocess.run([sys.executable, '-I', os.path.join(here, 'uirng.py'), 'A'] + sys.argv[2:], capture_output=True, text=True).stdout
    print('rng changes during UI:', out.count('CHANGED'))
r = subprocess.run([sys.executable, '-I', '-u', os.path.join(here, 'autoturn.py'), '1'], capture_output=True, text=True).stdout
print('\n'.join(l for l in r.splitlines() if l.startswith('turn') or l.startswith('    ') or 'STOP' in l or 'dialog' in l))
