"""Inspect / modify a system's player production queue in a running instance.
usage: queue.py <inst> show [owner]
       queue.py <inst> clear <sysidx>        (slotsUsed=0)
       queue.py <inst> swap <sysidx>         (swap entries 0 and 1)
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

SYS_PTR, SYS_CNT, SYS_SIZE = 0x5a36c8, 0x5a36bc, 0x328


def entries(q):
    out = []
    for i in range(4):
        e = struct.unpack_from('<ihhhhihhi', q, i * 24)
        out.append(dict(zip(('order', 'invested', 'unrest', 'build', 'upgrade', 'cost', 'ship', 'shipup', 'count'), e)))
    return out, struct.unpack_from('<iii', q, 96)


def main():
    inst, cmd = sys.argv[1], sys.argv[2]
    pid = H.load_state()[inst]
    sp = struct.unpack('<I', H.readmem(pid, SYS_PTR, 4))[0]
    cnt = struct.unpack('<H', H.readmem(pid, SYS_CNT, 2))[0]
    if cmd == 'show':
        owner = int(sys.argv[3]) if len(sys.argv) > 3 else None
        for i in range(cnt):
            s = H.readmem(pid, sp + i * SYS_SIZE, SYS_SIZE)
            ctl = s[0x4c]
            if owner is not None and ctl != owner:
                continue
            if ctl >= 5:
                continue
            name = s[8:0x30].split(b'\0')[0].decode('latin1')
            qp = struct.unpack_from('<I', s, 0xa8)[0]
            cur = struct.unpack_from('<ihhhhihh', s, 0x80)
            line = '%3d %-14s owner=%d cur(order=%d inv=%d build=%d cost=%d)' % (i, name, ctl, cur[0], cur[1], cur[3], cur[5])
            if qp:
                q = H.readmem(pid, qp, 0x6c)
                es, tail = entries(q)
                line += ' q@%08x slots=%d buy1st=%d ' % (qp, tail[0], tail[2]) + ' | '.join('b%d/o%d/c%d' % (e['build'], e['order'], e['cost']) for e in es[:tail[0] if 0 <= tail[0] <= 4 else 4])
            print(line)
        return
    idx = int(sys.argv[3])
    s = H.readmem(pid, sp + idx * SYS_SIZE, SYS_SIZE)
    qp = struct.unpack_from('<I', s, 0xa8)[0]
    q = bytearray(H.readmem(pid, qp, 0x6c))
    if cmd == 'clear':
        struct.pack_into('<i', q, 96, 0)
    elif cmd == 'fusion':
        # exactly what the UI wrote when "Type 2 Fusion Plant" (id 108) was double-clicked
        q[0:24] = bytes.fromhex('01000000000000006c000000000000000000000002000000')
        struct.pack_into('<ii', q, 96, 1, 1)
        cur = bytearray(s[0x80:0x94])
        struct.pack_into('<ihhh', cur, 0, 1, 0, 0, 108)
        h0 = H.kernel32.OpenProcess(0x0008 | 0x0020 | 0x0010 | 0x0400, False, pid)
        import ctypes
        w0 = ctypes.c_size_t()
        H.kernel32.WriteProcessMemory(h0, ctypes.c_void_p(sp + idx * SYS_SIZE + 0x80), bytes(cur), len(cur), ctypes.byref(w0))
        H.kernel32.CloseHandle(h0)
    elif cmd == 'swap':
        q[0:24], q[24:48] = q[24:48], q[0:24]
    h = H.kernel32.OpenProcess(0x0008 | 0x0020 | 0x0010 | 0x0400, False, pid)
    import ctypes
    wr = ctypes.c_size_t()
    H.kernel32.WriteProcessMemory(h, ctypes.c_void_p(qp), bytes(q), len(q), ctypes.byref(wr))
    H.kernel32.CloseHandle(h)
    print('wrote', wr.value)


if __name__ == '__main__':
    main()
