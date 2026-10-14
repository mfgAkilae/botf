#!/bin/bash
# usage: resume_n.sh <savedir> <exe> <host> <other...>   (generalised resume5.sh: any subset of A..E, any host)
# usage of the original: resume5.sh <savedir> [exe]   — restart all 5 instances from a saved checkpoint
# (<savedir>/auto_<X>.sav for X in A..E, written by savepoint.sh) instead of starting at turn 0.
# Host A: CONTINUE -> "continue as multiplayer" YES -> TCP/IP -> connect; B..E join and pick their race.
# The host only presses ACCEPT once all four other players are listed in its lobby ; a join that did not arrive is repeated. After loading, all five games must
# show the full player mask 0x1f, otherwise everything is restarted (up to 3 attempts).
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
H="python -I tools/harness.py"
SAV=$1; EXE=$2; HOST=$3; shift 3; OTHERS="$*"; ALL="$HOST $OTHERS"; NP=$(echo $ALL | wc -w)
declare -A RACEY=([A]=166 [B]=374 [C]=238 [D]=304 [E]=443) NAME=([A]=Alpha [B]=Beta [C]=Gamma [D]=Delta [E]=Epsilon)
for x in $ALL; do [ -s "$SAV/auto_$x.sav" ] || { echo "missing $SAV/auto_$x.sav"; exit 1; }; done

lobby_full() {   # all name rows of the host lobby are filled
  python -I - $NP $HOST <<'EOF2'
import sys; sys.path.insert(0, 'tools')
import harness as H
from PIL import Image
st = H.load_state(); H.capture(H.main_window(st[sys.argv[2]]), 'shots/lobby_now.png')
img = Image.open('shots/lobby_now.png').convert('RGB')
rows = sum(1 for y in (157, 180, 203, 226, 249) if sum(1 for x in range(375, 450) if sum(img.getpixel((x, y))) > 300) >= 5)
sys.exit(0 if rows == int(sys.argv[1]) else 1)
EOF2
}

joined() {    # are $1 players listed in the host lobby? (name rows 157/180/203/226/249)
  python -I - "$1" "$HOST" <<'EOF'
import sys; sys.path.insert(0, 'tools')
import harness as H
from PIL import Image
st = H.load_state(); H.capture(H.main_window(st[sys.argv[2]]), 'shots/lobby_now.png')
img = Image.open('shots/lobby_now.png').convert('RGB')
rows = sum(1 for y in (157, 180, 203, 226, 249) if sum(1 for x in range(375, 450) if sum(img.getpixel((x, y))) > 300) >= 5)
sys.exit(0 if rows >= int(sys.argv[1]) else 1)
EOF
}

join() {
  x=$1; nm=$2; ry=$3
  for try in 1 2 3; do
    $H click $x 705 215; sleep 3
    $H click $x 160 407; sleep 0.5; for i in 1 2 3 4 5 6 7 8; do $H key $x 08; done; $H text $x $nm; sleep 0.3
    $H click $x 80 262; sleep 2
    $H click $x 250 215; sleep 3
    $H click $x 405 270; sleep 1
    $H click $x 480 309; sleep 0.5; for i in 1 2 3 4 5 6 7 8 9 10; do $H key $x 08; done; $H text $x 127.0.0.1; sleep 0.5
    $H click $x 515 505; sleep 6
    $H click $x 400 244; sleep 1
    $H click $x 545 520; sleep 6
    $H click $x 230 $ry; sleep 2
    joined $NJ && return 0
    echo "join of $x did not arrive (try $try)"
    $H key $x 1b; sleep 1; $H key $x 1b; sleep 1; $H click $x 80 315; sleep 2   # back out
  done
  return 1
}

attempt() {
  for x in A B C D E; do $H kill $x >/dev/null 2>&1 || true; done
  sleep 2
  rm -f "$TEST"/?/dxwnd.lockfile.tmp
  tasklist | grep -qi dplaysvr || powershell -NoProfile -Command "Start-Process -FilePath '$(cygpath -w "$DPLAY/dplaysvr.exe")' -WorkingDirectory '$(cygpath -w "$DPLAY")' -WindowStyle Hidden"
  for x in $ALL; do
    cp "$EXE" $TEST/$x/trek.exe; : > $TEST/$x/Crash.log
    cp "$SAV/auto_$x.sav" $TEST/$x/auto.sav
  done
  for x in $ALL; do
    $H launch $x "$(cygpath -w "$TEST/$x")"; sleep 6
    if ! $H wins $x | head -1 | grep -q "800, 600)"; then
      echo "instance $x is not windowed 800x600, aborting"
      for y in A B C D E; do $H kill $y >/dev/null 2>&1 || true; done; exit 1
    fi
  done
  sleep 8
  $H click $HOST 705 122; sleep 4          # CONTINUE
  $H click $HOST 290 234; sleep 4          # continue as multiplayer: YES
  $H click $HOST 160 360; sleep 0.5; $H text $HOST testgame; sleep 0.3
  $H click $HOST 160 407; sleep 0.5; $H text $HOST ${NAME[$HOST]}; sleep 0.3
  $H click $HOST 405 270; sleep 1
  $H click $HOST 515 505; sleep 6          # connect -> empire selection
  NJ=1
  for x in $OTHERS; do NJ=$((NJ+1)); join $x ${NAME[$x]} ${RACEY[$x]} || return 1; done
  $H click $HOST 230 ${RACEY[$HOST]}; sleep 2
  lobby_full || { echo "host lobby not complete"; return 1; }
  $H click $HOST 545 520
  python -I - $ALL <<'EOF'
import sys, struct, time; sys.path.insert(0, 'tools')
import harness as H
st = H.load_state(); t0 = time.time(); r = {}
while time.time() - t0 < 300:
    r = {k: (struct.unpack('<I', H.readmem(st[k], 0x5a2918, 4))[0], H.readmem(st[k], 0x5a2b2a, 1)[0], H.readmem(st[k], 0x5a2b28, 1)[0])
         for k in sys.argv[1:] if H.pid_alive(st[k])}
    if len(r) == len(sys.argv) - 1 and len(set(v[0] for v in r.values())) == 1 and len(set(v[2] for v in r.values())) == 1 and all(v[1] != 255 for v in r.values()):
        print('loaded after %ds:' % (time.time() - t0), r); sys.exit(0)
    time.sleep(3)
print('NOT loaded completely:', r); sys.exit(1)
EOF
}

for n in 1 2 3; do
  if attempt; then for x in $ALL; do $H place $x; done; exit 0; fi
  echo "attempt $n failed, restarting"
done
for x in A B C D E; do $H kill $x >/dev/null 2>&1 || true; done
exit 1
