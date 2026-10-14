#!/bin/bash
# usage: probe.sh <label> <uirng actions on A...>  — do UI actions on idle A, play one turn, report diffs
cd "$(dirname "$0")/.." || exit 1                 # repository root
TEST=${BOTF_TEST:-$PWD/test}                       # game instances test/A .. test/E
DPLAY=${BOTF_DPLAY:-$PWD/dplay}                    # DirectPlay files (dplaysvr.exe, dpwsockx.dll)
L=$1; shift
echo "== $L"
[ $# -gt 0 ] && python -I tools/uirng.py A "$@" | grep -c CHANGED | sed 's/^/rng-changes during UI: /'
timeout 400 python -I -u tools/autoturn.py 1 2>&1 | grep -E '^turn|STOP|^    ' | head -8
