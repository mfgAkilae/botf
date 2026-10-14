"""Build function->source module map from assert file-name strings; report callers of given functions by module.
usage: modmap.py <export_dir> <func_hex> [<func_hex> ...]
"""
import re, bisect, collections, json, os, sys

d = sys.argv[1]
BS = chr(92)
fsrc = {}
for l in open(os.path.join(d, 'strings.txt'), encoding='utf-8'):
    parts = l.rstrip('\n').split('\t')
    if len(parts) < 3:
        continue
    s = parts[1]
    if not s.endswith('.c'):
        continue
    segs = s.split(BS)
    name = '/'.join(segs[-2:]) if len(segs) > 1 else s
    for m in re.finditer(r'([0-9a-f]{8})\((\w+)\)', parts[2]):
        fn = m.group(2)
        if fn.startswith('FUN_'):
            fsrc[int(fn[4:], 16)] = name

funcs = []
for l in open(os.path.join(d, 'functions.txt'), encoding='utf-8'):
    p = l.rstrip('\n').split('\t')
    funcs.append((int(p[0], 16), p[1], p[3] if len(p) > 3 else ''))
funcs.sort()
known = sorted(fsrc.items())
ka = [k for k, _ in known]


def module(a):
    if a in fsrc:
        return fsrc[a]
    i = bisect.bisect_right(ka, a) - 1
    lo = known[i] if i >= 0 else None
    hi = known[i + 1] if i + 1 < len(known) else None
    if lo and hi and lo[1] == hi[1]:
        return lo[1]
    return '~' + (lo[1] if lo else '?') + '..' + (hi[1] if hi else '?')


json.dump({'%08x' % a: module(a) for a, _, _ in funcs}, open(os.path.join(d, 'modmap.json'), 'w'), indent=0)
fa = {'%08x' % a: c for a, n, c in funcs}
for target in sys.argv[2:]:
    callers = fa[target].split()[1:]
    cnt = collections.defaultdict(list)
    for c in callers:
        cnt[module(int(c, 16))].append(c)
    print(target, len(callers))
    for k in sorted(cnt):
        print('   %-45s %s' % (k, ' '.join(cnt[k])))
