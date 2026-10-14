"""Classify remote kill-request executions in ktrace_<A|B>.log files of a longrun directory.
A request whose target seqno lies in the requester's own seqno range is a player action (the
requester's UI deleted its own order). A request matching any other live order is a wrong kill.
usage: khits.py <dir>"""
import glob, os, re, sys

BASES = [0, 0x2aaaaaaa, 0x55555555, 0x7fffffff, 0xaaaaaaaa, 0xd5555552]


def rng(seq):
    for i in range(len(BASES) - 1, -1, -1):
        if seq >= BASES[i]:
            return i
    return 0


d = sys.argv[1]; total = wrong = own = 0
for f in sorted(glob.glob(os.path.join(d, 'ktrace_?.log'))):
    lines = open(f, errors='replace').read().splitlines()
    for i, l in enumerate(lines):
        if 'kill-request payload' not in l:
            continue
        total += 1
        m = re.search(r'orders with seqno (\d+): (.*)', lines[i + 1]) if i + 1 < len(lines) else None
        k = next((x for x in lines[i + 1:i + 5] if 'KILL mode 2' in x), '')
        tm = re.match(r'\s*([\d.]+) turn (\d+)', k)
        src = re.search(r'emp=(\d+)', k)
        if not m or m.group(2) == 'NONE':
            continue
        tgt = int(m.group(1)); req = int(src.group(1)) if src else -1
        if rng(tgt) == req and req < 5:
            own += 1; kind = 'player action (own order)'
        else:
            wrong += 1; kind = 'WRONG KILL'
        print('%s turn %s: target %#x (range %d) from emp %d -> %s  [%s]' % (
            os.path.basename(f), tm.group(2) if tm else '?', tgt, rng(tgt), req, m.group(2)[:90], kind))
print('requests executed: %d, own-order kills: %d, wrong kills: %d' % (total, own, wrong))
