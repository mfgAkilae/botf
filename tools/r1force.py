"""Static audit R1 test: let the morale event of one system fire with a fixed roll in one game.
Run one process per instance at the same time, so every machine does exactly the same.
  0x43f527  cmp dword [edi+0x2f4], 0   event cooldown of the system in EDI -> set to 0 for the target system
  0x43f6b2  mov esi, edx               rand % 100 of FUN_0043f66c -> forced for the target system (emulated)
usage: r1force.py <inst> <sysidx> <roll> <seconds> [first_turn]   (env TRACER_STOP=<file>: stop early)"""
import ctypes, os, struct, sys, time
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbg import k32, DEBUG_EVENT, WOW64_CONTEXT, rpm, wpm, DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED
import harness as H
k32.DebugActiveProcess.argtypes = [wintypes.DWORD]; k32.DebugActiveProcessStop.argtypes = [wintypes.DWORD]
k32.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]; k32.OpenProcess.restype = wintypes.HANDLE
ROLL, CHK = 0x43f6b2, 0x43f527
KIND, ADD = 0x43fa14, 0x43fa4e   # logged (emulated): production kind [ecx], added industry [esp+0x348]
PRE, POST = 0x462471, 0x46252f   # logged (emulated): the target system's record before the production snapshot / after the loop


def ctx_of(tid):
    th = k32.OpenThread(0x1F03FF, False, tid)
    ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
    k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
    return th, ctx


def main():
    inst, sysidx, roll, dur = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
    first = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    pid = H.load_state()[inst]; stopf = os.environ.get('TRACER_STOP')
    hp = k32.OpenProcess(0x1F0FFF, False, pid)
    if not k32.DebugActiveProcess(pid): raise OSError(ctypes.get_last_error())
    k32.DebugSetProcessKillOnExit(False)
    orig = {}; step = None; t0 = time.time(); ev = DEBUG_EVENT()
    try:
        while time.time() - t0 < dur and not (stopf and os.path.exists(stopf)):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200): continue
            cont = DBG_CONTINUE
            if ev.dwDebugEventCode == 1:
                er = ev.u.Exception.ExceptionRecord; ec, addr = er.ExceptionCode, er.ExceptionAddress or 0
                bp = ec in (0x80000003, 0x4000001F)
                if bp and not orig:
                    for a in (ROLL, CHK, KIND, ADD, PRE, POST): orig[a] = rpm(hp, a, 1); wpm(hp, a, b'\xcc')
                    print('armed'); sys.stdout.flush()
                elif bp and addr in orig:
                    th, ctx = ctx_of(ev.dwThreadId)
                    sysptr = struct.unpack('<I', rpm(hp, 0x5a36c8, 4))[0] + sysidx * 0x328
                    turn = struct.unpack('<I', rpm(hp, 0x5a2918, 4))[0]
                    if addr in (PRE, POST):
                        print('turn %d %s production loop: system %d record %s' % (turn, 'before' if addr == PRE else 'after', sysidx, rpm(hp, sysptr + 0x80, 0x14).hex()))
                        if addr == PRE:
                            ctx.Edx = 0xff; ctx.Eip = PRE + 5
                        else:
                            tgt = (POST + 5 + struct.unpack('<i', rpm(hp, POST + 1, 4))[0]) & 0xffffffff
                            ctx.Esp -= 4; wpm(hp, ctx.Esp, struct.pack('<I', POST + 5)); ctx.Eip = tgt
                    elif addr == KIND:
                        rec = rpm(hp, ctx.Ecx, 0x14)
                        print('turn %d boost: production record %s' % (turn, rec.hex()))
                        ctx.Eax = struct.unpack('<I', rec[:4])[0]; ctx.Eip = KIND + 2
                    elif addr == ADD:
                        v = struct.unpack('<I', rpm(hp, ctx.Esp + 0x348, 4))[0]
                        print('turn %d boost: adds %d (0x%08x) to invested %d' % (turn, v, v, struct.unpack('<H', rpm(hp, ctx.Ecx + 4, 2))[0]))
                        ctx.Eax = v; ctx.Eip = ADD + 7
                    elif addr == CHK:
                        if ctx.Edi == sysptr and turn >= first:
                            print('turn %d system %d cooldown %d -> 0' % (turn, sysidx, struct.unpack('<i', rpm(hp, ctx.Edi + 0x2f4, 4))[0]))
                            wpm(hp, ctx.Edi + 0x2f4, bytes(4))
                        wpm(hp, CHK, orig[CHK]); ctx.Eip = CHK; ctx.EFlags |= 0x100; step = ev.dwThreadId
                    else:
                        s = struct.unpack('<h', rpm(hp, ctx.Esp + 0x35c, 2))[0]
                        if s == sysidx and turn >= first:
                            print('turn %d system %d roll %d -> %d (threshold %d)' % (turn, s, ctx.Edx, roll, ctx.Ecx))
                            ctx.Edx = roll
                        ctx.Esi = ctx.Edx; ctx.Eip = ROLL + 2
                    sys.stdout.flush()
                    k32.Wow64SetThreadContext(th, ctypes.byref(ctx)); k32.CloseHandle(th)
                elif ec in (0x4000001E, 0x80000004) and step == ev.dwThreadId:
                    wpm(hp, CHK, b'\xcc'); step = None
                elif bp or ec in (0x4000001E, 0x80000004):
                    pass
                else:
                    cont = DBG_EXCEPTION_NOT_HANDLED
            elif ev.dwDebugEventCode == 5:
                print('exited'); return
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        for a, o in orig.items(): wpm(hp, a, o)
        t1 = time.time(); quiet = time.time()
        while time.time() - t1 < 10 and (step or time.time() - quiet < 1.0):     # rewind threads already on an INT3
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 100): continue
            quiet = time.time()
            er = ev.u.Exception.ExceptionRecord
            if ev.dwDebugEventCode == 1:
                if er.ExceptionCode in (0x4000001E, 0x80000004):
                    step = None
                elif er.ExceptionCode in (0x80000003, 0x4000001F) and er.ExceptionAddress in orig:
                    th, ctx = ctx_of(ev.dwThreadId); ctx.Eip = er.ExceptionAddress
                    k32.Wow64SetThreadContext(th, ctypes.byref(ctx)); k32.CloseHandle(th)
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
        k32.DebugActiveProcessStop(pid); print('detached')


if __name__ == '__main__':
    main()
