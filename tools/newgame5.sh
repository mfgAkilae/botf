#!/bin/bash
# usage: newgame5.sh <exe>   — installs exe into test/A..E and starts a 5-human MP game:
# A host Cardassians, B Klingons, C Federation, D Ferengi, E Romulans; large ring galaxy, normal difficulty.
# Every test/<X>/dxwnd.dxw must point to its own folder, otherwise the game starts fullscreen.
set -e
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
H="python -I tools/harness.py"
EXE=${1:-trek_t_bug.exe}
for x in A B C D E; do $H kill $x >/dev/null 2>&1 || true; done
sleep 1
for x in A B C D E; do
  grep -qi "\\\\$x\\\\trek.exe" $TEST/$x/dxwnd.dxw || { echo "dxwnd.dxw of $x points elsewhere"; exit 1; }
  cp "$EXE" $TEST/$x/trek.exe; : > $TEST/$x/Crash.log
done
rm -f "$TEST"/?/dxwnd.lockfile.tmp      # stale after a crash: dxwnd does not hook, the game goes fullscreen
tasklist | grep -qi dplaysvr || powershell -NoProfile -Command "Start-Process -FilePath '$(cygpath -w "$DPLAY/dplaysvr.exe")' -WorkingDirectory '$(cygpath -w "$DPLAY")' -WindowStyle Hidden"
sleep 1
for x in A B C D E; do
  $H launch $x "$(cygpath -w "$TEST/$x")"; sleep 6
  if ! $H wins $x | head -1 | grep -q "800, 600)"; then
    echo "instance $x is not windowed 800x600, aborting"
    for y in A B C D E; do $H kill $y >/dev/null 2>&1 || true; done; exit 1
  fi
done
sleep 8
# host
$H click A 705 215; sleep 3
$H click A 160 360; sleep 0.5; $H text A testgame; sleep 0.3
$H click A 160 407; sleep 0.5; $H text A Alpha; sleep 0.3
$H click A 80 215; sleep 2
$H click A 250 215; sleep 3
$H click A 405 270; sleep 1
$H click A 515 505; sleep 6
$H click A 545 520; sleep 4
join() {
  x=$1; nm=$2; ry=$3
  $H click $x 705 215; sleep 3
  $H click $x 160 407; sleep 0.5; $H text $x $nm; sleep 0.3
  $H click $x 80 262; sleep 2
  $H click $x 250 215; sleep 3
  $H click $x 405 270; sleep 1
  $H click $x 480 309; sleep 0.5; $H text $x 127.0.0.1; sleep 0.3
  $H click $x 515 505; sleep 6
  $H click $x 400 244; sleep 1
  $H click $x 545 520; sleep 6
  $H click $x 230 $ry; sleep 2
}
join B Beta 374; join C Gamma 238; join D Delta 304; join E Epsilon 443
$H click A 230 166; sleep 2
$H click A 545 520; sleep 60
python -I - <<'EOF'
import sys, struct; sys.path.insert(0, 'tools')
import harness as H
st = H.load_state()
for k in 'ABCDE':
    p = st[k]
    print(k, 'alive', H.pid_alive(p), 'turn', struct.unpack('<I', H.readmem(p, 0x5a2918, 4))[0],
          'local', H.readmem(p, 0x5a2b2a, 1)[0], 'mask', hex(H.readmem(p, 0x5a2b28, 1)[0]))
EOF
for x in A B C D E; do $H place $x; done   # dxwnd may move the windows after the mode switch
