"""Summarise remote kill-request executions in ktrace logs of a run directory: requests from turn
processing that matched a live order on the receiver are wrong kills.
usage: hits.py <dir>"""
import glob, os, re, sys
d = sys.argv[1]; total = hits = 0
for f in sorted(glob.glob(os.path.join(d, 'rng_t*_?.log'))):
    lines = open(f).read().splitlines()
    for i, l in enumerate(lines):
        if 'kill-request payload' in l:
            total += 1
            m = re.search(r'orders with seqno (\d+): (.*)', lines[i + 1]) if i + 1 < len(lines) else None
            k = next((x for x in lines[i + 1:i + 6] if 'KILL mode 2' in x), '')
            src = re.search(r'emp=(\d+)', k)
            if m and m.group(2) != 'NONE':
                tgt = int(m.group(1)); req = int(src.group(1)) if src else -1
                own = tgt < 0xd5555552 and tgt // 0x2aaaaaaa == req
                kind = 'player action (own order)' if own else 'TURN PROCESSING -> WRONG KILL'
                if not own: hits += 1
                print('%s: target %#x from emp %s -> %s  [%s]' % (os.path.basename(f), tgt, req, m.group(2), kind))
print('requests executed: %d, wrong kills by turn-processing requests: %d' % (total, hits))
