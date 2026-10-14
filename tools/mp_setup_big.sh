#!/bin/bash
# Host on A, prepare join on B (localhost). Screens captured to shots/.
cd /e/dev/botf/work
H="python -I tools/harness.py"
# --- host A
$H click A 705 215; sleep 3
$H click A 160 360; sleep 0.5; $H text A testgame; sleep 0.3
$H click A 160 407; sleep 0.5; $H text A Alpha; sleep 0.3
$H click A 80 215; sleep 2
$H click A 250 215; sleep 3
$H click A 405 270; sleep 1
$H click A 515 505; sleep 6
for y in 220 284 348 411 475; do for k in 1 2 3; do $H click A 90 $y; sleep 0.6; done; done
$H click A 545 475; sleep 1
$H shot A shots/cfg_big.png
$H click A 405 351; sleep 1
$H click A 545 520; sleep 4
$H shot A shots/mp_a1.png
# --- join B
$H click B 705 215; sleep 3
$H click B 160 407; sleep 0.5; $H text B Beta; sleep 0.3
$H click B 80 262; sleep 2
$H click B 250 215; sleep 3
$H click B 405 270; sleep 1
$H click B 480 309; sleep 0.5; $H text B 127.0.0.1; sleep 0.3
$H shot B shots/mp_b1.png
