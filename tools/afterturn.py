"""Player changes something AFTER pressing TURN (while waiting for the other player).
usage: afterturn.py <action> [--who A]   actions: labor | build | energy | none
Prints the system labor/flags before and after, and the heartbeat comparison after the turn."""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from autoturn import u32, i32, TURN_ADDR, BUSY_ADDR, TURN_BTN, snapshot, compare, force_active, Dialogs, handle_dialogs
st = H.load_state(); P = {'A': st['A'], 'B': st['B']}; dlg = Dialogs()
act = sys.argv[1]; who = sys.argv[sys.argv.index('--who') + 1] if '--who' in sys.argv else 'A'
other = 'B' if who == 'A' else 'A'
TABS = {'A': {'prod': (94, 94), 'energy': (94, 122), 'build': (94, 150)}, 'B': {'prod': (90, 87), 'energy': (90, 115), 'build': (90, 143)}}
def key(inst, vk):
    hw = H.main_window(P[inst]); H.user32.PostMessageW(hw, 0x100, vk, 1); time.sleep(0.03); H.user32.PostMessageW(hw, 0x101, vk, 0xC0000001)
def click(inst, x, y, w=0.6):
    H.click(H.main_window(P[inst]), x, y, pid=P[inst]); time.sleep(w)
def home_sys(inst):
    pid = P[inst]; sp = u32(pid, 0x5a36c8); cnt = struct.unpack('<H', H.readmem(pid, 0x5a36bc, 2))[0]
    loc = H.readmem(pid, 0x5a2b2a, 1)[0]
    for i in range(cnt):
        s = H.readmem(pid, sp + i * 0x328, 0x328)
        if s[0x4c] == loc and s[8:0x30].split(b'\0')[0] in (b'Cardassia', b"Qo'nos"): return i
def sysinfo(inst, idx):
    pid = P[inst]; s = H.readmem(pid, u32(pid, 0x5a36c8) + idx * 0x328, 0x328)
    return 'labor %s upd %d/%d auto %d cur %s' % (struct.unpack_from('<5i', s, 0x54), struct.unpack_from('<i', s, 0x314)[0], struct.unpack_from('<i', s, 0x318)[0], struct.unpack_from('<i', s, 0x324)[0], s[0x80:0x94].hex())
def press(inst, t):
    for _ in range(6):
        if i32(P[inst], BUSY_ADDR) != 0 or u32(P[inst], TURN_ADDR) > t: return True
        handle_dialogs(dlg, inst, P[inst], print)
        click(inst, *TURN_BTN[inst], w=0.3)
        for _ in range(10):
            time.sleep(0.3)
            if i32(P[inst], BUSY_ADDR) != 0 or u32(P[inst], TURN_ADDR) > t: return True
    return False
force_active(P)
idx = home_sys(who); t = u32(P['A'], TURN_ADDR)
print('turn', t, 'home system index', idx)
print('before      ', who, sysinfo(who, idx), '|', other, sysinfo(other, idx))
key(who, 0x70); time.sleep(0.5)
assert press(who, t); print(who, 'pressed TURN, busy', i32(P[who], BUSY_ADDR))
time.sleep(1)
if act != 'none':
    click(who, 522, 238); key(who, 0x71); time.sleep(1)
    if act == 'labor':
        click(who, *TABS[who]['prod']); click(who, 430, 100)
    elif act == 'build':
        click(who, *TABS[who]['build']); click(who, 300, 113); click(who, 300, 129)
    elif act == 'energy':
        click(who, *TABS[who]['energy']); click(who, 270, 218)
    H.capture(H.main_window(P[who]), 'shots/afterturn_%s.png' % act)
    key(who, 0x70); time.sleep(0.5)
print('after action', who, sysinfo(who, idx), '|', other, sysinfo(other, idx))
assert press(other, t); print(other, 'pressed TURN')
t0 = time.time()
while not all(u32(P[x], TURN_ADDR) > t and i32(P[x], BUSY_ADDR) == 0 for x in 'AB'):
    if time.time() - t0 > 4: handle_dialogs(dlg, 'A', P['A'], print); handle_dialogs(dlg, 'B', P['B'], print)
    time.sleep(1)
    if time.time() - t0 > 180: print('timeout'); break
time.sleep(1.5)
print('after turn  ', who, sysinfo(who, idx), '|', other, sysinfo(other, idx))
rep = compare(snapshot(P['A']), snapshot(P['B']))
print('diffs:', len(rep)); [print('   ', x) for x in rep[:10]]
print('HEARTBEAT MISMATCH' if any(x.startswith(('RNG', 'CRC')) for x in rep) else 'heartbeat ok')
