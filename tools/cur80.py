"""Print the current-production kind (+0x80), invested (+0x84) and build or ship id (+0x88/+0x90) of every system owned by the empire of <inst>
on all five instances, plus the queue head of the owner.
usage: cur80.py <inst> [system index ...]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
st = H.load_state(); own = sys.argv[1]; only = [int(x) for x in sys.argv[2:]]
emp = H.readmem(st[own], 0x5a2b2a, 1)[0]


def systems(pid):
    sp = struct.unpack('<I', H.readmem(pid, 0x5a36c8, 4))[0]
    cnt = struct.unpack('<H', H.readmem(pid, 0x5a36bc, 2))[0]
    return [H.readmem(pid, sp + i * 0x328, 0x328) for i in range(cnt)]


al = {x: systems(st[x]) for x in 'ABCDE'}
for i, s in enumerate(al[own]):
    if s[0x4c] != emp or (only and i not in only):
        continue
    name = s[8:0x30].split(b'\0')[0].decode('latin1')
    row = ' '.join('%s:%d/%d/%d' % (x, struct.unpack_from('<i', al[x][i], 0x80)[0], struct.unpack_from('<h', al[x][i], 0x84)[0],
                                     struct.unpack_from('<h', al[x][i], 0x88 if al[x][i][0x80] != 3 else 0x90)[0]) for x in 'ABCDE')
    q = struct.unpack_from('<I', s, 0xa8)[0]
    head = ''
    if q:
        qb = H.readmem(st[own], q, 0x6c)
        n = struct.unpack_from('<i', qb, 96)[0]
        head = ' queue ' + ' '.join('o%d/inv%d/id%d/cost%d' % (struct.unpack_from('<i', qb, k * 24)[0], struct.unpack_from('<h', qb, k * 24 + 4)[0],
                                     struct.unpack_from('<h', qb, k * 24 + (16 if qb[k * 24] == 3 else 8))[0], struct.unpack_from('<i', qb, k * 24 + 12)[0]) for k in range(max(0, min(n, 4))))
    print('%3d %-14s %s%s' % (i, name, row, head))
