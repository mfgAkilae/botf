#!/bin/bash
# Fix L reproduction: manual combat B vs E from saves/war5_01_t280 (tools/tactest.sh); everybody is processing
# (busy 1). The host A broadcasts its options (FUN_0050d320 run in a new thread, as when it closes the options
# dialog) while the clients are processing. Original: clients hit "conninit.c line 617" and quit.
# usage: opt85.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
bash tools/tactest.sh $1 "" 0 | tail -1
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; from autoturn import i32,BUSY_ADDR; st=H.load_state(); print('busy', {x: i32(st[x],BUSY_ADDR) for x in 'ABCDE'})"
python -I tools/remotecall.py A 50d320                 # host broadcasts its options (message 0x85)
sleep 6
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; st=H.load_state(); print('alive', {x: H.pid_alive(st[x]) for x in 'ABCDE'})"
for x in A B C D E; do [ -s ${BOTF_TEST:-test}/$x/Crash.log ] && { echo "Crash.log $x:"; sed -n 4,6p ${BOTF_TEST:-test}/$x/Crash.log; }; done
