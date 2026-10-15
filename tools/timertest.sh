#!/bin/bash
# Fix K check: turn-200..: host A switches the strategic timer on (options), opens "delete current build?" at
# Cardassia, the timer is set to expire, and we look whether A ends its turn while the dialog is open.
# usage: timertest.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1
sleep 3
$H key A 1b; sleep 1.5; $H click A 700 362; sleep 1.5
for i in 1 2; do $H click A 475 452; sleep 0.5; done          # STRATEGIC TIMER > None
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; from autoturn import screen; screen('A', H.load_state()['A'], '../shots/tt_opt')"
$H click A 545 528; sleep 2; $H click A 705 122; sleep 3      # ACCEPT, CONTINUE
$H key A 70; sleep 0.8; $H click A 535 190; sleep 0.8; $H key A 71; sleep 1.5; $H click A 94 150; sleep 1
$H click A 638 270; sleep 1.5                                 # "industry invested. Delete current build?"
python -I - <<'PY'
import sys, struct, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, BUSY_ADDR, screen
st = H.load_state(); a = st['A']
u = lambda ad: struct.unpack('<i', H.readmem(a, ad, 4))[0]
print('timer', u(0x593064), 'paused', u(0x59305c), 'dispatch depth', u(0x6897b0))
screen('A', a, '../shots/tt_dlg')
H.writemem(a, 0x593064, struct.pack('<i', 0))
time.sleep(4)
print('after expiry: busy A', i32(a, BUSY_ADDR), 'timer', u(0x593064), 'paused', u(0x59305c))
screen('A', a, '../shots/tt_after')
PY
