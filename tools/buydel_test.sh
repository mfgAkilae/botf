#!/bin/bash
# Natural desync found by the agents (run nat5_bug_1402, turn 331): replay player B's inputs of turn 330 at
# Qo'nos (system 43) from the turn-330 save: delete the build the turn processing had just started (after an
# item bought the turn before completed), pick new structures and a ship, end the turn.
# usage: buydel_test.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
H="python -I tools/harness.py"
EXE=$1
timeout 900 bash tools/resume_n.sh saves/hb_1402_t330 $EXE B C E | tail -1
sleep 3
python -I tools/sysdiag.py 43 B C | grep -E "turn|rec80|order"
python -I - <<'EOF'
import sys, struct, time; sys.path.insert(0, 'tools')
import harness as H
st = H.load_state(); p = st['B']; hw = H.main_window(p)
def key(vk):
    H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)
def click(x, y, w):
    H.click(hw, x, y, pid=p); time.sleep(w)
key(0x70); time.sleep(0.5)
ui = struct.unpack('<I', H.readmem(p, 0x595da8, 4))[0]; H.writemem(p, ui + 0x1c, struct.pack('<h', 43))
key(0x71); time.sleep(0.9)
click(90, 143, 0.9); click(638, 280, 1.6); click(300, 177, 0.9); click(300, 193, 0.8)
click(90, 171, 0.9); click(300, 129, 0.8); key(0x70); time.sleep(0.6)
EOF
python -I tools/sysdiag.py 43 B C | grep -E "turn|rec80|order"
for i in 1 2; do echo "== turn $i"; python -I tools/turn5.py 43 | grep -E "^turn|MISMATCH|sys 43"; done
