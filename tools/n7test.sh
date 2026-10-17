#!/bin/bash
# Fix HA reproduction (review finding N7, shipyard loss arm A): from checkpoint saves/five_1201_t103 Cardassian
# player A gets a second Heavy Cruiser queued at Cardassia (system 5, queue entry 1 = copy of entry 0) and buys the
# current one. At the end of turn 103 only A starts the queued ship (record +0x80: A 3, B..E 0). In turn 104 A scraps
# the Union Shipyard. Without the fix only A kills the ship order -> heartbeat mismatch at turn 105.
# usage: n7test.sh <exe>
cd "$(dirname "$0")/.." || exit 1                 # repository root
H="python -I tools/harness.py"
bash tools/resume5.sh saves/five_1201_t103 $1 | tail -1
sleep 3
python -I - <<'PY'
import sys, struct, ctypes; sys.path.insert(0, 'tools'); import harness as H
pid = H.load_state()['A']
sp = struct.unpack('<I', H.readmem(pid, 0x5a36c8, 4))[0]
q = struct.unpack('<I', H.readmem(pid, sp + 5 * 0x328 + 0xa8, 4))[0]
qb = bytearray(H.readmem(pid, q, 0x6c)); qb[24:48] = qb[0:24]
h = H.kernel32.OpenProcess(0x0008 | 0x0020 | 0x0010 | 0x0400, False, pid); w = ctypes.c_size_t()
H.kernel32.WriteProcessMemory(h, ctypes.c_void_p(q), bytes(qb), len(qb), ctypes.byref(w))
PY
$H key A 70; sleep 0.8; $H click A 535 190; sleep 0.8; $H key A 71; sleep 1.5
$H click A 94 150; sleep 1; $H click A 640 198; sleep 1.2; $H click A 330 226; sleep 1.2   # BUILD LIST, BUY, BUY
$H key A 70; sleep 0.8
python -I tools/turn5.py 5 | grep -E "^turn|MISMATCH"
python -I tools/cur80.py A 5
$H key A 70; sleep 0.8; $H click A 535 190; sleep 0.8; $H key A 71; sleep 1.5
$H click A 94 207; sleep 1.2                                   # STRUCTURES
for i in 1 2 3 4; do $H click A 552 437; sleep 1; done          # page with the Union Shipyard
$H click A 278 355; sleep 1.2                                  # "Scrap Union Shipyard?"
$H click A 318 226; sleep 1.2                                  # YES
$H key A 70; sleep 0.8
for i in 1 2 3; do python -I tools/turn5.py 5 | grep -E "^turn|MISMATCH"; python -I tools/cur80.py A 5; done
