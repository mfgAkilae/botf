"""Intel commit while waiting: <inst> ends the turn, opens the intel screen (F3), changes the internal-security
share in the screen's data ([[0x5cb4b4]+0x1c], what the slider writes) and leaves the screen (F1), which commits.
Prints internal security (+0x70) of that empire's intel record on every instance before and after.
usage: intelwait.py <inst> [delta]"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import i32, BUSY_ADDR
TURN = {'A': (163, 33), 'B': (110, 22), 'C': (130, 22), 'D': (150, 22), 'E': (180, 22)}
x = sys.argv[1]; delta = int(sys.argv[2]) if len(sys.argv) > 2 else 10
st = H.load_state(); p = st[x]; hw = H.main_window(p)
def k(vk):
    H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001); time.sleep(0.8)
emp = H.readmem(p, 0x5a2b2a, 1)[0]
rec = lambda q: [struct.unpack('<i', H.readmem(st[q], 0x5a3aec + emp * 0x2c1c + 0x70 + 4 * i, 4))[0] for i in range(9)]
print('before', {q: rec(q)[0] for q in 'ABCDE'})
k(0x70); H.click(hw, *TURN[x], pid=p); time.sleep(1); print(x, 'busy', i32(p, BUSY_ADDR))
k(0x72); time.sleep(1)
ui = struct.unpack('<I', H.readmem(p, 0x5cb4b4, 4))[0]
vals = [struct.unpack('<i', H.readmem(p, ui + 0x1c + 4 * i, 4))[0] for i in range(9)]
print('ui', vals)
# move points from the first non-zero espionage/sabotage slot to security (the total stays 100)
j = next((i for i in range(1, 9) if vals[i] >= delta), None)
if j is None:                                            # all on security: give the first espionage slot some
    j, delta = 1, -delta
vals[0] += delta; vals[j] -= delta
if True:
    for i in (0, j):
        H.writemem(p, ui + 0x1c + 4 * i, struct.pack('<i', vals[i]))
k(0x70); time.sleep(1)
print('after ', {q: rec(q)[0] for q in 'ABCDE'})
