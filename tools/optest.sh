#!/bin/bash
# Fix OP check: client B's local preference for random events is the opposite of the game's setting. B ends the
# turn; while B waits for the others it opens OPTIONS and presses ACCEPT (no change in the dialog). Original: B's
# game switches random events locally (no broadcast while waiting) -> different random numbers -> mismatch within
# a few turns; fixed: B keeps the game's setting and everybody stays in sync.
# usage: optest.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1
sleep 3
python -I - <<'PY'
import sys, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, BUSY_ADDR
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state()
def k(x, vk):
    hw = H.main_window(st[x]); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001); time.sleep(0.6)
def turn(x):
    k(x, 0x70); H.click(H.main_window(st[x]), *TURN[x], pid=st[x]); time.sleep(0.8)
rev = H.readmem(st['B'], 0x5a2b46, 1)[0]
H.writemem(st['B'], 0x5b1a3d, bytes([1 - rev]))          # B's preference: the opposite
print('game random events', rev, '-> B preference', 1 - rev)
turn('B'); print('B busy', i32(st['B'], BUSY_ADDR))
hw = H.main_window(st['B'])
k('B', 0x1b); time.sleep(1)
for xy in ((700, 362), (545, 528), (705, 122)):          # OPTIONS, ACCEPT, CONTINUE
    H.click(hw, *xy, pid=st['B']); time.sleep(1.5)
print('after options', {x: H.readmem(st[x], 0x5a2b46, 1)[0] for x in 'ABCDE'}, 'B busy', i32(st['B'], BUSY_ADDR))
for x in 'ACDE':
    turn(x)
PY
for i in 1 2 3 4 5; do timeout 300 python -I tools/turn5.py 2>&1 | grep "^turn\|MISMATCH\|rror" | head -3 | cut -c1-150; done
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; st=H.load_state(); print('random events', {x: H.readmem(st[x],0x5a2b46,1)[0] for x in 'ABCDE'})"
