"""Attach to a running 32-bit trek.exe and log hits of breakpoints (re-armed via single step).
usage: tracer.py <pid> <seconds> <va_hex[=label]> ...
Prints: time, thread, label, eax/ebx/ecx/edx/esi/edi, [esp] .. [esp+8]
Detaches cleanly (process keeps running).
"""
import ctypes, os, struct, sys, time
from ctypes import wintypes
sys.path.insert(0, __file__.rsplit('\\', 1)[0])
from dbg import (k32, DEBUG_EVENT, WOW64_CONTEXT, rpm, wpm, DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED)

k32.DebugActiveProcess.argtypes = [wintypes.DWORD]
k32.DebugActiveProcessStop.argtypes = [wintypes.DWORD]
k32.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]
k32.OpenProcess.restype = wintypes.HANDLE


STACK = int(os.environ.get('STACK', '0'))


def main():
    pid = int(sys.argv[1])
    dur = float(sys.argv[2])
    bps = {}
    for a in sys.argv[3:]:
        va, _, label = a.partition('=')
        bps[int(va, 16)] = label or va
    hp = k32.OpenProcess(0x1F0FFF, False, pid)
    if not k32.DebugActiveProcess(pid):
        raise OSError(ctypes.get_last_error())
    k32.DebugSetProcessKillOnExit(False)
    orig = {}
    armed = False
    pending_rearm = {}  # thread -> addr
    t0 = time.time()
    ev = DEBUG_EVENT()
    try:
        stopf = os.environ.get('TRACER_STOP')
        while time.time() - t0 < dur and not (stopf and os.path.exists(stopf)):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200):
                continue
            code = ev.dwDebugEventCode
            cont = DBG_CONTINUE
            if code == 1:
                er = ev.u.Exception.ExceptionRecord
                ec, addr = er.ExceptionCode, er.ExceptionAddress or 0
                if ec in (0x80000003, 0x4000001F) and not armed and addr not in orig:
                    for b in bps:
                        orig[b] = rpm(hp, b, 1)
                        wpm(hp, b, bytes([0xCC]))
                    armed = True
                    print('%7.3f armed %d bps' % (time.time() - t0, len(bps))); sys.stdout.flush()
                elif ec == 0x4000001F and addr in orig:
                    th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                    ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
                    k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
                    st = struct.unpack('<3I', rpm(hp, ctx.Esp, 12).ljust(12, bytes(1)))
                    print('%7.3f tid=%5d %-24s eax=%08x ebx=%08x ecx=%08x edx=%08x esi=%08x edi=%08x [esp]=%08x %08x %08x' % (
                        time.time() - t0, ev.dwThreadId, bps[addr], ctx.Eax, ctx.Ebx, ctx.Ecx, ctx.Edx, ctx.Esi, ctx.Edi, *st))
                    if STACK:
                        raw = rpm(hp, ctx.Esp, 0x600)
                        ra = []
                        for o in range(0, len(raw) - 3, 4):
                            v = struct.unpack_from('<I', raw, o)[0]
                            if 0x401000 <= v < 0x570000 and rpm(hp, v - 5, 1) == bytes([0xe8]):
                                ra.append('%06x' % v)
                            if len(ra) >= STACK:
                                break
                        busy = struct.unpack('<i', rpm(hp, 0x5a291c, 4))[0]
                        print('        busy=%d stack: %s' % (busy, ' '.join(ra)))
                    sys.stdout.flush()
                    wpm(hp, addr, orig[addr])
                    ctx.Eip = addr
                    ctx.EFlags |= 0x100  # single step to re-arm
                    k32.Wow64SetThreadContext(th, ctypes.byref(ctx))
                    k32.CloseHandle(th)
                    pending_rearm[ev.dwThreadId] = addr
                elif ec in (0x4000001E, 0x80000004) and ev.dwThreadId in pending_rearm:
                    a = pending_rearm.pop(ev.dwThreadId)
                    if time.time() - t0 < dur:
                        wpm(hp, a, bytes([0xCC]))
                elif ec in (0x80000003, 0x4000001F, 0x4000001E, 0x80000004):
                    pass
                else:
                    cont = DBG_EXCEPTION_NOT_HANDLED
            elif code == 5:
                print('process exited'); return
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        for b, o in orig.items():
            wpm(hp, b, o)
        # drain pending single steps so no trap fires after detach
        t1 = time.time()
        while pending_rearm and time.time() - t1 < 5:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200):
                continue
            if ev.dwDebugEventCode == 1:
                ec = ev.u.Exception.ExceptionRecord.ExceptionCode
                if ec in (0x4000001E, 0x80000004):
                    pending_rearm.pop(ev.dwThreadId, None)
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
        k32.DebugActiveProcessStop(pid)
        print('%7.3f detached' % (time.time() - t0))


if __name__ == '__main__':
    main()
