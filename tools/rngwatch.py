"""Report the HB-compared part of the main RNG block (0x596bac, 0x120 bytes, offsets 4..0x17 excluded)
for both instances. usage: rngwatch.py [save NAME | diff NAME]"""
import hashlib, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

def state(pid):
    b = bytearray(H.readmem(pid, 0x596bac, 0x120))
    b[4:0x18] = bytes(0x14)
    return bytes(b)

st = H.load_state()
cur = {n: state(st[n]) for n in 'AB'}
for n in 'AB':
    print(n, 'seed %08x' % struct.unpack_from('<I', cur[n])[0], 'hash', hashlib.md5(cur[n]).hexdigest()[:12])
print('A==B', cur['A'] == cur['B'])
