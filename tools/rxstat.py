"""Print turn, busy and length of the DPMP receive packet list [0x5a0dfc] for both instances."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

st = H.load_state()
for n in 'AB':
    p = st[n]
    lp = struct.unpack('<I', H.readmem(p, 0x5a0dfc, 4))[0]
    cnt = struct.unpack('<i', H.readmem(p, lp + 4, 4))[0] if lp else -1
    print(n, 'turn', struct.unpack('<I', H.readmem(p, 0x5a2918, 4))[0], 'busy', struct.unpack('<i', H.readmem(p, 0x5a291c, 4))[0], 'rxlist', cnt)
