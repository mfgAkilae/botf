#!/bin/bash
# Fix HB (review finding N15): a slower player's checksums (0x71) that arrive after this player ended his next turn.
# From saves/five_1201_t103, B runs a --slowend build (stays in the turn calculation 30 s longer) and gets a poked
# divergence (morale of one system); everybody ends the turn; as soon as A has finished the calculation it ends the
# next turn (state -1), so B's checksums reach A while A waits. A breakpoint trace on A logs the two mismatch branches
# (0x5100c9 turn-end compare, 0x51031f compare on arrival). Without the fix A never compares B's checksums.
# usage: hbtest.sh <exe> <slow exe for B>
cd "$(dirname "$0")/.." || exit 1                 # repository root
EXE_B=$2 bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1 | cut -c1-60
sleep 3
python -I - <<'PY'
import sys, struct; sys.path.insert(0, 'tools'); import harness as H
pid = H.load_state()['B']
sp = struct.unpack('<I', H.readmem(pid, 0x5a36c8, 4))[0]; a = sp + 5 * 0x328 + 0x2dc
v = struct.unpack('<h', H.readmem(pid, a, 2))[0]; H.writemem(pid, a, struct.pack('<h', v + 7)); print('B system 5 morale', v, '->', v + 7)
PY
rm -f $TEMP/hbstop; PA=$(python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; print(H.load_state()['A'])")
(TRACER_STOP=$TEMP/hbstop STACKBPS=5100c9,51031f python -I -u tools/ktrace.py $PA 120 > turnlog/hbtrace_A.txt 2>&1 &); sleep 4
python -I - <<'PY'
import sys, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import u32, i32, force_active
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state(); P = {x: st[x] for x in 'ABCDE'}
def press(x):
    hw = H.main_window(P[x]); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.3); H.click(hw, *TURN[x], pid=P[x])
t = u32(P['A'], 0x5a2918)
for x in 'ABCDE':
    press(x); time.sleep(0.3)
t0 = time.time()
while not (u32(P['A'], 0x5a2918) > t and i32(P['A'], 0x5a291c) == 0) and time.time() - t0 < 120:
    force_active(P); time.sleep(0.2)
print('A finished turn %d after %.0fs; B busy %d' % (t, time.time() - t0, i32(P['B'], 0x5a291c)))
press('A')
for _ in range(20):
    time.sleep(0.2)
    if i32(P['A'], 0x5a291c) != 0: break
print('A ended the next turn: busy %d, B busy %d' % (i32(P['A'], 0x5a291c), i32(P['B'], 0x5a291c)))
t1 = time.time()
while i32(P['B'], 0x5a291c) == 1 and time.time() - t1 < 60:
    force_active(P); time.sleep(0.5)
time.sleep(5)
print('B finished, A busy %d' % i32(P['A'], 0x5a291c))
PY
touch $TEMP/hbstop; sleep 3
echo "mismatch branch hits on A:"; grep STACKBP turnlog/hbtrace_A.txt | cut -c1-120
