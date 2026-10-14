"""Replicate the installer's file selection for {tmp}\\vanilla\\mod (component vanilla, language en,
tasks vanillab800 + displayw) and build stbof.res (zip deflate).
usage: stage_vanilla.py <install_script.iss> <extract_root> <out_stbof.res> [lang] [tasks,comma,separated]
"""
import os, re, sys, zipfile

iss, root, out = sys.argv[1], sys.argv[2], sys.argv[3]
lang = sys.argv[4] if len(sys.argv) > 4 else 'en'
tasks = set((sys.argv[5] if len(sys.argv) > 5 else 'vanillab800,displayw').lower().split(','))
BS = chr(92)
prefix = '{tmp}' + BS + 'vanilla' + BS + 'mod' + BS

text = open(iss, 'rb').read().decode('utf-8-sig', errors='replace')
field = re.compile(r'(\w+):\s*("([^"]*)"|[^;]*);')
sel = {}
for line in text.splitlines():
    if not line.startswith('Source:'):
        continue
    f = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(2).strip()) for m in field.finditer(line)}
    src = f.get('source', '')
    if not src.lower().startswith(prefix):
        continue
    comps = f.get('components', '').lower().split()
    if 'vanilla' not in comps:
        continue
    langs = f.get('languages', '').strip()
    if langs and lang not in langs.split():
        continue
    texpr = f.get('tasks', '').strip().lower()
    if texpr:
        expr = re.sub(r'[a-z_][a-z0-9_]*', lambda m: m.group(0) if m.group(0) in ('and', 'or', 'not') else str(m.group(0) in tasks), texpr)
        if not eval(expr):
            continue
    rel = src[len('{tmp}' + BS):]
    destname = f.get('destname') or src.split(BS)[-1]
    sel[destname.lower()] = (rel, destname)

print('selected', len(sel))
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
    for key in sorted(sel):
        rel, destname = sel[key]
        path = os.path.join(root, '{tmp}', *rel.split(BS))
        if not os.path.exists(path):
            # innounp lowercases nothing; try case-insensitive lookup
            dirp = os.path.dirname(path)
            cand = [n for n in os.listdir(dirp) if n.lower() == os.path.basename(path).lower()]
            if not cand:
                print('missing', path)
                continue
            path = os.path.join(dirp, cand[0])
        z.write(path, destname)
print('wrote', out)
