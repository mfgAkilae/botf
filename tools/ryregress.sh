#!/bin/bash
# Fix RY regression on the five-instance test bed (each step resumes saves/five_1201_t103):
#   1 automatic repair (tools/spike.py auto, divergence on C, 3 more turns)
#   2 a player without RY (tools/rymixed.py: CANCEL after the ACK wait, stock error, nothing loaded)
#   3 host leaves the session during the ACK wait, and host killed during the ACK wait (tools/ryabort.py)
#   4 repair after a host migration (tools/rymigrate.py)
#   5 a leaver's orders that reached only some machines (tools/porders.sh)
# Exit status: the number of failed steps (a failed resume, a crash, a timeout or a failed check).
# usage: ryregress.sh <ry exe> <exe without RY> <logdir>
cd "$(dirname "$0")/.." || exit 1                 # repository root
EXE=$1; OLD=$2; D=$3; mkdir -p $D
FAILED=()
step() { echo "=== $1 $(date +%T)"; }
resume() {        # resume five instances; EXE_E=... in the environment gives E another exe
  local r; r=$(bash tools/resume5.sh saves/five_1201_t103 $EXE | tail -1); echo "$r"
  echo "$r" | grep -q "^loaded after"
}
run() {           # run <name> <cmd...>: record a failure when the command fails or times out
  local name=$1; shift
  "$@"; local rc=$?
  [ $rc -ne 0 ] && { FAILED+=("$name (exit $rc)"); echo "FAIL $name: exit $rc"; }
  return 0
}

step 1-auto
if resume; then sleep 3
  run 1-auto env SPIKE_JSON=$EXE.json timeout 900 python -I tools/spike.py auto --diverge C:5 --turns 3 > $D/1_auto.txt 2>&1
  grep -E " ok$|FAIL|checksum words equal after" $D/1_auto.txt
  grep -q " FAIL$" $D/1_auto.txt && FAILED+=("1-auto (check)")
  grep -q "checksum words equal after 3 of 3" $D/1_auto.txt || FAILED+=("1-auto (turns)")
else FAILED+=("1-auto (resume)"); fi

step 2-mixed
if EXE_E=$OLD resume; then sleep 3
  run 2-mixed timeout 600 python -I -u tools/rymixed.py $EXE E C 5 > $D/2_mixed.txt 2>&1; grep -E "ok$|FAIL|RESULT" $D/2_mixed.txt
else FAILED+=("2-mixed (resume)"); fi

step 3a-session
if EXE_E=$OLD resume; then sleep 3
  run 3a-session timeout 300 python -I -u tools/ryabort.py $EXE E session > $D/3a_session.txt 2>&1; grep -E "ok$|FAIL|RESULT" $D/3a_session.txt
else FAILED+=("3a-session (resume)"); fi

step 3b-kill
if EXE_E=$OLD resume; then sleep 3
  run 3b-kill timeout 500 python -I -u tools/ryabort.py $EXE E kill > $D/3b_kill.txt 2>&1; grep -E "ok$|FAIL|RESULT" $D/3b_kill.txt
else FAILED+=("3b-kill (resume)"); fi

step 4-migrate
if resume; then sleep 3
  run 4-migrate timeout 1500 python -I -u tools/rymigrate.py $EXE 5 > $D/4_migrate.txt 2>&1; grep -E "ok$|FAIL|RESULT" $D/4_migrate.txt
else FAILED+=("4-migrate (resume)"); fi

step 5-porders
run 5-porders bash tools/porders.sh $EXE > $D/5_porders.txt 2>&1
grep -E "RESULT|^turn" $D/5_porders.txt | cut -c1-200
grep -q "RESULT advanced" $D/5_porders.txt || FAILED+=("5-porders (turn)")
grep -q "MISMATCH" $D/5_porders.txt && FAILED+=("5-porders (mismatch)")
[ "$(grep -c '^turn' $D/5_porders.txt)" -ge 3 ] || FAILED+=("5-porders (turns)")

step done
if [ ${#FAILED[@]} -eq 0 ]; then echo "ALL PASSED"; else printf 'FAILED: %s\n' "${FAILED[@]}"; fi
exit ${#FAILED[@]}
