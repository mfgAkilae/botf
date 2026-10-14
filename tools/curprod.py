"""Print current-production fields (+0x80..+0xa8) and queue head of a system on both instances.
usage: curprod.py <system name>"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
name = sys.argv[1].encode(); st = H.load_state()
for n in 'AB':
    pid = st[n]; sp = struct.unpack('<I', H.readmem(pid, 0x5a36c8, 4))[0]
    cnt = struct.unpack('<H', H.readmem(pid, 0x5a36bc, 2))[0]
    for i in range(cnt):
        s = H.readmem(pid, sp + i * 0x328, 0x328)
        if s[8:0x30].split(b'\0')[0] == name:
            q = struct.unpack_from('<I', s, 0xa8)[0]
            print(n, i, 'cur', s[0x80:0x94].hex(), 'last', s[0x94:0xa8].hex(), 'q0', H.readmem(pid, q, 0x18).hex(), 'qtail', H.readmem(pid, q + 0x60, 0xc).hex())
