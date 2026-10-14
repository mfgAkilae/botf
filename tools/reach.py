"""Which roots reach which targets in the static call graph (functions.txt caller lists).
usage: reach.py targets=a,b roots=x,y [path]"""
import sys, collections
callees = collections.defaultdict(set)
for line in open('export_en/functions.txt'):
    parts = line.rstrip('\n').split('\t')
    if len(parts) < 4 or not parts[3].startswith('callers:'):
        continue
    f = int(parts[0], 16)
    for c in parts[3][8:].split():
        callees[int(c, 16)].add(f)
args = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
targets = {int(x, 16) for x in args['targets'].split(',')}
for r in [int(x, 16) for x in args['roots'].split(',')]:
    prev = {r: None}
    q = collections.deque([r])
    hits = []
    while q:
        f = q.popleft()
        if f in targets and f != r:
            hits.append(f)
            continue
        for g in callees[f]:
            if g not in prev:
                prev[g] = f
                q.append(g)
    out = []
    for h in hits:
        path = [h]
        while prev[path[-1]] is not None:
            path.append(prev[path[-1]])
        out.append(' < '.join('%06x' % p for p in path))
    print('%06x: %s' % (r, ('\n    ' + '\n    '.join(out)) if out else '-'))
