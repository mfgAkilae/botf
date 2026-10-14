import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32
st = H.load_state(); idx = int(sys.argv[1])
for k in 'ABCDE':
    p = st[k]; s = H.readmem(p, u32(p, 0x5a36c8) + idx * 0x328, 0x328)
    print(k, 'turn', u32(p, 0x5a2918), 'rec80..99', s[0x80:0x9a].hex(), '86=%d' % struct.unpack_from('<h', s, 0x86)[0],
          'morale', struct.unpack_from('<h', s, 0x2dc)[0], 'mlvl', struct.unpack_from('<h', s, 0x2de)[0], 'flags2e0', s[0x2e0:0x2f0].hex())
