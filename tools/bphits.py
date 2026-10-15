"""Log every hit of a set of code breakpoints in one game (registers + turn/busy).
usage: bphits.py <inst> <seconds> <addr_hex> ...   (env TRACER_STOP=<file>: stop early)
Uses INT3 + single step; meant for main-thread code (other threads could pass while a breakpoint is lifted)."""
import ctypes, os, struct, sys, time
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbg import k32, DEBUG_EVENT, WOW64_CONTEXT, rpm, wpm, DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED
import harness as H
k32.DebugActiveProcess.argtypes = [wintypes.DWORD]; k32.DebugActiveProcessStop.argtypes = [wintypes.DWORD]
k32.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]; k32.OpenProcess.restype = wintypes.HANDLE


def main():
    inst, dur = sys.argv[1], float(sys.argv[2]); bps = [int(a, 16) for a in sys.argv[3:]]
    pid = H.load_state()[inst]; stopf = os.environ.get('TRACER_STOP')
    hp = k32.OpenProcess(0x1F0FFF, False, pid)
    if not k32.DebugActiveProcess(pid): raise OSError(ctypes.get_last_error())
    k32.DebugSetProcessKillOnExit(False)
    orig = {}; pend = {}; t0 = time.time(); ev = DEBUG_EVENT()
    try:
        while time.time() - t0 < dur and not (stopf and os.path.exists(stopf)):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200): continue
            cont = DBG_CONTINUE
            if ev.dwDebugEventCode == 1:
                er = ev.u.Exception.ExceptionRecord; ec, addr = er.ExceptionCode, er.ExceptionAddress or 0
                if ec in (0x80000003, 0x4000001F) and not orig:
                    for b in bps: orig[b] = rpm(hp, b, 1); wpm(hp, b, b'\xcc')
                    print('armed'); sys.stdout.flush()
                elif ec in (0x80000003, 0x4000001F) and addr in orig:
                    th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                    ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
                    k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
                    turn = struct.unpack('<I', rpm(hp, 0x5a2918, 4))[0]; busy = struct.unpack('<i', rpm(hp, 0x5a291c, 4))[0]
                    print('%7.3f turn %d busy %d hit %06x eax %08x ebx %08x ecx %08x edx %08x esi %08x edi %08x esp %08x ret %08x' % (
                        time.time() - t0, turn, busy, addr, ctx.Eax, ctx.Ebx, ctx.Ecx, ctx.Edx, ctx.Esi, ctx.Edi, ctx.Esp,
                        struct.unpack('<I', rpm(hp, ctx.Esp, 4))[0])); sys.stdout.flush()
                    wpm(hp, addr, orig[addr]); ctx.Eip = addr; ctx.EFlags |= 0x100
                    k32.Wow64SetThreadContext(th, ctypes.byref(ctx)); k32.CloseHandle(th); pend[ev.dwThreadId] = addr
                elif ec in (0x4000001E, 0x80000004) and ev.dwThreadId in pend:
                    wpm(hp, pend.pop(ev.dwThreadId), b'\xcc')
                elif ec in (0x80000003, 0x4000001F, 0x4000001E, 0x80000004):
                    pass
                else:
                    cont = DBG_EXCEPTION_NOT_HANDLED
            elif ev.dwDebugEventCode == 5:
                print('exited'); return
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        for b, o in orig.items(): wpm(hp, b, o)
        t1 = time.time(); quiet = time.time()
        while time.time() - t1 < 10 and (pend or time.time() - quiet < 1.0):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 100): continue
            quiet = time.time()
            er = ev.u.Exception.ExceptionRecord
            if ev.dwDebugEventCode == 1:
                if er.ExceptionCode in (0x4000001E, 0x80000004):
                    pend.pop(ev.dwThreadId, None)
                elif er.ExceptionCode in (0x80000003, 0x4000001F) and er.ExceptionAddress in orig:
                    th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                    ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
                    k32.Wow64GetThreadContext(th, ctypes.byref(ctx)); ctx.Eip = er.ExceptionAddress
                    k32.Wow64SetThreadContext(th, ctypes.byref(ctx)); k32.CloseHandle(th)
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
        k32.DebugActiveProcessStop(pid); print('detached')


if __name__ == '__main__':
    main()
