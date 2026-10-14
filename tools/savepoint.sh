#!/bin/bash
# usage: savepoint.sh <name>   — copy every instance's auto.sav (written by the game after each turn) to
# saves/<name>_t<turn>/auto_<X>.sav, so resume5.sh can restart from there. Call only while all games are idle.
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
T=$(python -I -c "import sys,struct; sys.path.insert(0,'tools'); import harness as H; print(struct.unpack('<I', H.readmem(H.load_state()['A'], 0x5a2918, 4))[0])")
D=saves/$1_t$T; mkdir -p $D
for x in A B C D E; do cp $TEST/$x/auto.sav $D/auto_$x.sav; done
echo $D
