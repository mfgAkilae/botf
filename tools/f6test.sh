#!/bin/bash
# Fix F6 A/B test: resume a 5-human checkpoint with <exe>, press F6 on B, play two turns with turn5.py and report
# the event flag, the monster countdown and whether the games stayed in sync.
# usage: f6test.sh <exe> <savedir>
cd "$(dirname "$0")/.." || exit 1                 # repository root
EXE=$1; SAV=$2
bash tools/resume5.sh $SAV $EXE | tail -1
sleep 3
show() {
  python -I -c "
import sys,struct; sys.path.insert(0,'tools'); import harness as H
st=H.load_state()
print('$1', {x:(struct.unpack('<I',H.readmem(st[x],0x5a2918,4))[0], H.readmem(st[x],0x5a2b46,1).hex(), H.readmem(st[x],0x5a2b6c,1).hex(), struct.unpack('<i',H.readmem(st[x],0x58fdb0,4))[0]) for x in 'ABCDE'})"
}
show 'before (turn, random events, flag, countdown)'
python -I tools/harness.py key B 75 >/dev/null; sleep 1
show 'after F6 on B'
for i in 1 2; do python -I tools/turn5.py 2>&1 | grep -v "^ *$" | head -6 | cut -c1-120; done
show 'after two turns'
