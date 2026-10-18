#!/bin/bash
# Review finding R5: a battle participant leaves after acknowledging a combat round. Manual combat B vs E from
# saves/war5_01_t280 (as tools/tactest.sh); both pick FIGHT, E ends the first round (TURN in the tactical view),
# then E's game is closed and B ends the round (and every later round). Without the fix B waits forever in the
# round barrier.
# KILL=D: a player outside the battle leaves instead (D); B and E then end every round.
# usage: r5leave.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
EXE=$1
bash tools/resume5.sh saves/war5_01_t280 $EXE | tail -1
sleep 3
$H key A 1b; sleep 1.5; $H click A 700 362; sleep 1.5; $H click A 340 354; sleep 1; $H click A 545 422; sleep 1
$H click A 545 528; sleep 2; $H click A 705 122; sleep 3
for x in A B C D E; do : > ../test/$x/Crash.log; done
python -I - <<'PY'
import sys, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, BUSY_ADDR
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
st = H.load_state()
for x in 'ABCDE':
    hw = H.main_window(st[x]); H.user32.PostMessageW(hw, 0x100, 0x70, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, 0x70, 0xC0000001)
    time.sleep(0.6); H.click(hw, *TURN[x], pid=st[x]); time.sleep(0.6)
time.sleep(20)
print('busy', {x: i32(st[x], BUSY_ADDR) for x in 'ABCDE'})
PY
$H click E 140 272; sleep 0.5; $H click B 278 408; sleep 8              # FIGHT on both
$H click E 95 25; sleep 3                                               # E ends the first round
python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; st=H.load_state(); print('player table', [(hex(H.u32 if False else int.from_bytes(H.readmem(st['A'],0x5a29f8+i*0x34+0x28,4),'little')), H.readmem(st['A'],0x5a29f8+i*0x34+0x2c,1)[0]) for i in range(5)])"
if [ -n "$TRACE" ]; then   # TRACE=<inst>: log the leave handler on that instance (tools/ktrace.py, stop file)
  rm -f $TEMP/r5stop; PT=$(python -I -c "import sys; sys.path.insert(0,'tools'); import harness as H; print(H.load_state()['$TRACE'])")
  if [ -n "$WATCH" ]; then   # WATCH="addr[:len] ...": hardware write watchpoints instead (tools/wtrace.py)
    (TRACER_STOP=$TEMP/r5stop python -I -u tools/wtrace.py $PT 300 $WATCH > turnlog/r5trace_$TRACE.txt 2>&1 &); sleep 4
  else
    (TRACER_STOP=$TEMP/r5stop STACKBPS=${TRACEBPS:-50d730,50d8f8,46fd60,4750f3,46ff99} python -I -u tools/ktrace.py $PT 300 > turnlog/r5trace_$TRACE.txt 2>&1 &); sleep 4
  fi
fi
K=${KILL:-E}
$H kill $K; sleep 5                                                     # the player leaves
for xy in A,400,386 B,305,266 C,236,344 D,300,336 E,210,292; do IFS=, read x cx cy <<< "$xy"; [ $x = $K ] || $H click $x $cx $cy; done   # CLOSE "... Disconnected" (per race skin)
$H click B 95 25                                                        # B ends the round
python -I - <<'PY'
import sys, time; sys.path.insert(0, 'tools'); import harness as H
from autoturn import i32, u32, force_active
import os
K = os.environ.get('KILL', 'E')
st = H.load_state(); P = {x: st[x] for x in 'ABCDE' if x != K}
t0 = time.time(); shot = False
while time.time() - t0 < 180:
    force_active(P)
    if all(u32(P[x], 0x5a2918) > 280 and i32(P[x], 0x5a291c) == 0 for x in P):
        break
    if not shot and time.time() - t0 > 15:
        for x in P:
            H.capture(H.main_window(P[x]), 'shots/r5_%s15.png' % x)
        shot = True
    if time.time() - t0 > 20:
        for x, xy in (('A', (400, 386)), ('B', (305, 266)), ('C', (236, 344)), ('D', (300, 336)), ('E', (210, 292))):
            if x in P:
                H.click(H.main_window(P[x]), *xy, pid=P[x])            # CLOSE a late "Disconnected" message
        for x in 'BE':
            if x in P:
                H.click(H.main_window(P[x]), 95, 25, pid=P[x])       # END / TURN for the next rounds
    time.sleep(6)
print('after %ds:' % (time.time() - t0), {x: (H.pid_alive(P[x]), u32(P[x], 0x5a2918), i32(P[x], 0x5a291c), H.readmem(P[x], 0x5a2b28, 1).hex()) for x in P})
print('player table', [(int.from_bytes(H.readmem(P['A'], 0x5a29f8 + i * 0x34 + 0x28, 4), 'little'), H.readmem(P['A'], 0x5a29f8 + i * 0x34 + 0x2c, 1)[0]) for i in range(5)])
H.capture(H.main_window(P['B']), 'shots/r5_B.png')
PY
for x in A B C D E; do [ -s ../test/$x/Crash.log ] && { echo "Crash.log $x:"; sed -n 4,6p ../test/$x/Crash.log; }; done
[ -n "$TRACE" ] && { touch $TEMP/r5stop; sleep 3; grep -v "^armed" turnlog/r5trace_$TRACE.txt | cut -c1-220 | head -20; }
