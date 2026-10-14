"""Sample the main thread of a running 32-bit trek.exe: EIP + code return addresses found on the stack.
usage: sampler.py <inst> <seconds> [interval_ms]
"""
import collections, ctypes, os, struct, sys, time, json
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from dbg import WOW64_CONTEXT, k32, rpm

TH32CS_SNAPTHREAD = 4


class THREADENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ThreadID', wintypes.DWORD),
                ('th32OwnerProcessID', wintypes.DWORD), ('tpBasePri', ctypes.c_long), ('tpDeltaPri', ctypes.c_long), ('dwFlags', wintypes.DWORD)]


def threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def main():
    inst, secs = sys.argv[1], float(sys.argv[2])
    iv = float(sys.argv[3]) / 1000 if len(sys.argv) > 3 else 0.05
    pid = H.load_state()[inst]
    tid = threads(pid)[0]          # first thread = main thread
    hp = k32.OpenProcess(0x1F0FFF, False, pid)
    th = k32.OpenThread(0x1F03FF, False, tid)
    mm = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'export_en', 'modmap.json')))
    funcs = sorted(int(a, 16) for a in mm)
    import bisect

    def fn(a):
        i = bisect.bisect_right(funcs, a) - 1
        return '%08x' % funcs[i] if i >= 0 else '?'

    eips = collections.Counter()
    stacks = collections.Counter()
    t0 = time.time()
    n = 0
    while time.time() - t0 < secs:
        k32.SuspendThread(th)
        ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
        k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
        st = rpm(hp, ctx.Esp, 0x400)
        k32.ResumeThread(th)
        n += 1
        eip = ctx.Eip
        if 0x401000 <= eip < 0x574000:
            eips[fn(eip)] += 1
        else:
            eips['ext'] += 1
        rets = []
        for i in range(0, len(st) - 3, 4):
            v = struct.unpack_from('<I', st, i)[0]
            if 0x401000 <= v < 0x574000:
                rets.append(fn(v))
                if len(rets) >= 6:
                    break
        stacks[' < '.join(rets)] += 1
        time.sleep(iv)
    print('samples', n)
    for k, v in eips.most_common(8):
        print('EIP %-10s %5d  %s' % (k, v, mm.get(k, '')))
    for k, v in stacks.most_common(6):
        print('%5d  %s' % (v, k))


if __name__ == '__main__':
    main()
