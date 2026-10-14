"""Hardware write-watchpoints (DR0-DR3) on a running 32-bit trek.exe; logs each write with EIP, new value, stack.
usage: wtrace.py <pid> <seconds> <addr_hex[:len]> ...   (len 1,2,4; default 4)
Env TRACER_STOP=<file>: stop when the file exists."""
import ctypes, os, struct, sys, time
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbg import k32, DEBUG_EVENT, WOW64_CONTEXT, rpm, DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED
k32.DebugActiveProcess.argtypes = [wintypes.DWORD]
k32.DebugActiveProcessStop.argtypes = [wintypes.DWORD]
k32.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]
k32.OpenProcess.restype = wintypes.HANDLE
from sampler import threads

LENBITS = {1: 0, 2: 1, 4: 3}

def set_drs(th, watches, clear=False):
    ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10010
    k32.SuspendThread(th)
    k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
    dr7 = 0
    for i, (a, n) in enumerate(watches):
        ctx.Dr[i] = 0 if clear else a
        if not clear:
            dr7 |= (1 << (i * 2)) | ((0b01 | (LENBITS[n] << 2)) << (16 + i * 4))
    ctx.Dr[5] = dr7  # Dr array: Dr0,Dr1,Dr2,Dr3,Dr6,Dr7
    ctx.Dr[4] = 0
    k32.Wow64SetThreadContext(th, ctypes.byref(ctx))
    k32.ResumeThread(th)

def main():
    pid = int(sys.argv[1]); dur = float(sys.argv[2])
    watches = []
    for a in sys.argv[3:]:
        x, _, n = a.partition(':'); watches.append((int(x, 16), int(n or 4)))
    hp = k32.OpenProcess(0x1F0FFF, False, pid)
    if not k32.DebugActiveProcess(pid):
        raise OSError(ctypes.get_last_error())
    k32.DebugSetProcessKillOnExit(False)
    ths = {}
    stopf = os.environ.get('TRACER_STOP')
    t0 = time.time(); ev = DEBUG_EVENT(); armed = False
    try:
        while time.time() - t0 < dur and not (stopf and os.path.exists(stopf)):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200):
                continue
            code = ev.dwDebugEventCode; cont = DBG_CONTINUE
            if code in (2, 3):  # create thread/process: arm later via thread list refresh
                pass
            if code == 1:
                er = ev.u.Exception.ExceptionRecord; ec = er.ExceptionCode
                if ec in (0x80000003, 0x4000001F) and not armed:
                    for tid in threads(pid):
                        th = k32.OpenThread(0x1F03FF, False, tid); ths[tid] = th; set_drs(th, watches)
                    armed = True
                    print('%7.3f armed %d threads' % (time.time() - t0, len(ths))); sys.stdout.flush()
                elif ec in (0x80000004, 0x4000001E):
                    th = ths.get(ev.dwThreadId) or k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                    ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10017
                    k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
                    dr6 = ctx.Dr[4]
                    hit = [i for i in range(len(watches)) if dr6 & (1 << i)]
                    raw = rpm(hp, ctx.Esp, 0x400); ra = []
                    for o in range(0, len(raw) - 3, 4):
                        v = struct.unpack_from('<I', raw, o)[0]
                        if 0x401000 <= v < 0x570000 and rpm(hp, v - 5, 1) == bytes([0xe8]):
                            ra.append('%06x' % v)
                        if len(ra) >= 8: break
                    busy = struct.unpack('<i', rpm(hp, 0x5a291c, 4))[0]
                    for i in hit:
                        a, n = watches[i]
                        print('%7.3f tid=%d w%d %08x=%s eip=%08x busy=%d stack %s' % (time.time() - t0, ev.dwThreadId, i, a,
                              rpm(hp, a, n).hex(), ctx.Eip, busy, ' '.join(ra)))
                    sys.stdout.flush()
                    ctx.Dr[4] = 0; ctx.ContextFlags = 0x10010
                    k32.Wow64SetThreadContext(th, ctypes.byref(ctx))
                elif ec in (0x80000003, 0x4000001F):
                    pass
                else:
                    cont = DBG_EXCEPTION_NOT_HANDLED
            elif code == 2 and armed:
                th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId); ths[ev.dwThreadId] = th
                try: set_drs(th, watches)
                except Exception: pass
            elif code == 5:
                print('process exited'); return
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        for tid, th in ths.items():
            try: set_drs(th, watches, clear=True)
            except Exception: pass
        k32.DebugActiveProcessStop(pid)
        print('%7.3f detached' % (time.time() - t0))

if __name__ == '__main__':
    main()
