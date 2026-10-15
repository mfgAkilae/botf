#!/bin/bash
# Fix Q check: new 2-player game (A, B humans, three computer empires that colonize a lot in the first turns).
# tools/colinject.py makes the first colonize mission that executes find its task force without a colony ship
# (colony-ship id -1, as after combat). Original: access violation at 0x469ad4 (both games end); fixed: the
# order is dropped, the games go on and stay in sync.
# usage: coltest.sh <exe> <turns>
cd "$(dirname "$0")/.." || exit 1                 # repository root
for x in A B; do [ -f ../test/$x/Crash.log ] && mv ../test/$x/Crash.log ../test/$x/Crash.log.$(date +%s); done
bash tools/newgame.sh $1 | tail -2
sleep 3
.venv/Scripts/python.exe -I tools/colinject.py
timeout 1500 python -I tools/autoturn.py $2 2>&1 | grep -E "^turn|MISMATCH|rror|dead|stuck|exit" | cut -c1-160
.venv/Scripts/python.exe -I tools/colinject.py status
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; st=H.load_state(); print({x: H.pid_alive(st[x]) for x in 'AB'})"
ls -la ../test/A/Crash.log ../test/B/Crash.log 2>&1 | cut -c1-120
