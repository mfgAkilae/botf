"""Print disassembly for an address range or whole function(s) from export asm.txt.
usage: asm.py <export_dir> <start_hex> [end_hex]      (no end => whole function at start)
       asm.py <export_dir> f <addr_hex> [<addr_hex> ...]  (whole functions)
"""
import sys, re, os

d = sys.argv[1]
lines = open(os.path.join(d, 'asm.txt'), encoding='utf-8').read().splitlines()


def addr(l):
    m = re.match(r'^([0-9a-f]{8})\s', l)
    return int(m.group(1), 16) if m else None


def func(fa):
    out = []
    on = False
    tag = ';==== FUNC %08x' % fa
    for l in lines:
        if l.startswith(';==== FUNC'):
            on = l.startswith(tag)
            if on:
                out.append(l)
            continue
        if on:
            out.append(l[:130])
    return out


if sys.argv[2] == 'f':
    for a in sys.argv[3:]:
        print('\n'.join(func(int(a, 16))))
else:
    s = int(sys.argv[2], 16)
    if len(sys.argv) > 3:
        e = int(sys.argv[3], 16)
        for l in lines:
            if l.startswith(';===='):
                continue
            a = addr(l)
            if a is not None and s <= a < e:
                print(l[:130])
    else:
        print('\n'.join(func(s)))
