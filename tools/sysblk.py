"""Show the 0x58-byte solar-building blocks (GUI copy +0x240, real copy +0x298) of a system on both instances.
usage: sysblk.py <system name>"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

name = sys.argv[1].encode()
st = H.load_state()
for n in 'AB':
    pid = st[n]
    sp = struct.unpack('<I', H.readmem(pid, 0x5a36c8, 4))[0]
    cnt = struct.unpack('<H', H.readmem(pid, 0x5a36bc, 2))[0]
    for i in range(cnt):
        s = H.readmem(pid, sp + i * 0x328, 0x328)
        if s[8:0x30].split(b'\0')[0] == name:
            print(n, 'sys', i, 'turn', struct.unpack('<I', H.readmem(pid, 0x5a2918, 4))[0])
            print('  gui ', s[0x240:0x298].hex())
            print('  real', s[0x298:0x2f0].hex())
