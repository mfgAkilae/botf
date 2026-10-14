"""Perform UI clicks on one instance and report after each whether the HB-compared main RNG changed.
usage: uirng.py <inst> x,y[,dbl|r|esc] ..."""
import os, struct, sys, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

def state(pid):
    b = bytearray(H.readmem(pid, 0x596bac, 0x120))
    b[4:0x18] = bytes(0x14)
    return bytes(b)

inst = sys.argv[1]
pid = H.load_state()[inst]
hw = H.main_window(pid)
prev = state(pid)
for i, a in enumerate(sys.argv[2:]):
    parts = a.split(',')
    if parts[0] == 'esc' or parts[0].startswith('k'):
        vk = 0x1b if parts[0] == 'esc' else int(parts[0][1:], 16)
        H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.05); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)
    else:
        x, y = int(parts[0]), int(parts[1])
        mode = parts[2] if len(parts) > 2 else ''
        H.click(hw, x, y, right=(mode == 'r'), pid=pid)
        if mode == 'dbl':
            time.sleep(0.05)
            H.click(hw, x, y, pid=pid)
    time.sleep(2.0)
    cur = state(pid)
    shot = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shots', 'ui_%s_%02d.png' % (inst, i))
    H.capture(hw, shot)
    print('%-14s rng %s seed %08x' % (a, 'CHANGED' if cur != prev else 'same', struct.unpack_from('<I', cur)[0]))
    prev = cur
