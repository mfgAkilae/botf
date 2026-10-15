#!/bin/bash
# Static audit R1 reproduction: from saves/five_1201_t103 Cardassian player A replaces the build at Cardassia
# (system 5; queue emptied, then a ship + Type 8 Hydroponic Farm). The ship completes in turn 105; only the
# owner starts the farm (production record = structure), the others' record stays 0 until their production loop.
# The boost in turn 106: owner invested = full cost (done), the others add stale stack data (+100) -> not done. the others' = 0 until their production loop), every
# machine gets the same high morale (200; the boost needs roll 41..50 < |150 - morale|) and cooldown 0 for that system, and the morale-event roll of that
# system is forced to 41 ("production boost") on all five. Original: the owner completes the build at once,
# the others add stale stack data -> sync error.
# usage: r1test.sh <exe> <logdir>
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
EXE=$1; D=$2; mkdir -p $D; rm -f $D/r1.stop
bash tools/resume5.sh saves/five_1201_t103 $EXE | tail -1
sleep 3
$H key A 70; sleep 0.8; $H click A 535 190; sleep 0.8; $H key A 71; sleep 1.5; $H click A 94 150; sleep 1
$H click A 638 270; sleep 1.2                  # Heavy Cruiser at the head: "industry invested. Delete current build?"
$H click A 318 226; sleep 1.2                  # YES -> Type 8 Fusion Plants becomes the head (owner only)
for i in 1 2 3 4 5 6 7; do $H click A 638 270; sleep 1; done   # clear the rest of the queue (2+1+4 items)
$H click A 94 178; sleep 1; $H click A 300 175; sleep 1.2     # SHIPBUILDING: ship class 1 (3 turns) as the head
$H click A 94 150; sleep 1; $H click A 300 95; sleep 1.2      # BUILD LIST: Type 8 Hydroponic Farm (3760 industry, 2 turns) next
$H key A 70; sleep 0.8
poke() { python -I - <<'PY'
import sys, struct; sys.path.insert(0, 'tools'); import harness as H
st = H.load_state()
for x in 'ABCDE':
    pid = st[x]; s = struct.unpack('<I', H.readmem(pid, 0x5a36c8, 4))[0] + 5 * 0x328
    H.writemem(pid, s + 0x2dc, struct.pack('<H', 200)); H.writemem(pid, s + 0x2f4, struct.pack('<I', 0))
print('morale 200, cooldown 0 for system 5 on all machines')
PY
}
poke
sleep 0; for x in A B C D E; do TRACER_STOP=$D/r1.stop python -I -u tools/r1force.py $x 5 41 600 106 > $D/r1force_$x.log 2>&1 & done
sleep 3
for i in 1 2 3 4 5; do echo "== turn $i"; [ $i -gt 1 ] && poke; python -I tools/turn5.py 5 | grep -E "^turn|MISMATCH|sys 5 [AB]"; python -I tools/sysdiag.py 5 A B | grep -E "queue|blk298"; done
touch $D/r1.stop; sleep 3; grep -h "roll" $D/r1force_*.log | sort | uniq -c
