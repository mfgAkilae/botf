#!/bin/bash
# usage: newgame.sh <exe>   — installs exe into test/A and test/B, starts a 2-player MP game (A host Cardassian, B Klingon)
set -e
cd /e/dev/botf/work
H="python -I tools/harness.py"
EXE=${1:-trek_test.exe}
EXEB=${2:-$EXE}
$H kill A >/dev/null 2>&1 || true
$H kill B >/dev/null 2>&1 || true
sleep 1
cp "$EXE" ../test/A/trek.exe
cp "$EXEB" ../test/B/trek.exe
: > ../test/A/Crash.log; : > ../test/B/Crash.log
$H launch A 'E:\dev\botf\test\A'
sleep 3
$H launch B 'E:\dev\botf\test\B'
sleep 14
bash tools/mp_setup.sh >/dev/null
$H click B 515 505; sleep 6          # connect
$H click B 400 244; sleep 1          # select session
$H click B 545 520; sleep 6          # join
$H click B 230 374; sleep 2          # B: Klingon
$H click A 230 166; sleep 2          # A: Cardassian
$H click A 545 520; sleep 25         # host accept -> start
$H shot A shots/ng_a.png >/dev/null
$H shot B shots/ng_b.png >/dev/null
python -I -c "
import sys,struct; sys.path.insert(0,'tools'); import harness as H
st=H.load_state()
for n in 'AB': print(n, 'turn', struct.unpack('<I',H.readmem(st[n],0x5a2918,4))[0], 'mp', struct.unpack('<I',H.readmem(st[n],0x5a2924,4))[0])
"
