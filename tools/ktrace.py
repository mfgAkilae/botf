"""Log order kills: at FUN_004576c4 entry the key (seqno, turn gen, emp) and mode; after the search the matched order header.
usage: ktrace.py <pid> <seconds>   (env TRACER_STOP)"""
import ctypes, os, struct, sys, time
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbg import k32, DEBUG_EVENT, WOW64_CONTEXT, rpm, wpm, DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED
k32.DebugActiveProcess.argtypes = [wintypes.DWORD]; k32.DebugActiveProcessStop.argtypes = [wintypes.DWORD]
k32.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]; k32.OpenProcess.restype = wintypes.HANDLE
ONLY2 = os.environ.get('ONLY2') == '1'
BPS = {0x4576c4: 'kill', 0x45770f: 'found2', 0x4577ca: 'found0'}
u32 = lambda hp, a: struct.unpack('<I', rpm(hp, a, 4))[0]

def stack(hp, esp):
    raw = rpm(hp, esp, 0x300); ra = []
    for o in range(0, len(raw) - 3, 4):
        v = struct.unpack_from('<I', raw, o)[0]
        if 0x401000 <= v < 0x570000 and rpm(hp, v - 5, 1) == bytes([0xe8]):
            ra.append('%06x' % v)
        if len(ra) >= 6: break
    return ' '.join(ra)

def main():
    pid = int(sys.argv[1]); dur = float(sys.argv[2]); stopf = os.environ.get('TRACER_STOP')
    hp = k32.OpenProcess(0x1F0FFF, False, pid)
    if not k32.DebugActiveProcess(pid): raise OSError(ctypes.get_last_error())
    k32.DebugSetProcessKillOnExit(False)
    orig = {}; armed = False; pend = {}; t0 = time.time(); ev = DEBUG_EVENT()
    try:
        while time.time() - t0 < dur and not (stopf and os.path.exists(stopf)):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200): continue
            cont = DBG_CONTINUE
            if ev.dwDebugEventCode == 1:
                er = ev.u.Exception.ExceptionRecord; ec, addr = er.ExceptionCode, er.ExceptionAddress or 0
                if ec in (0x80000003, 0x4000001F) and not armed and addr not in orig:
                    for b in BPS: orig[b] = rpm(hp, b, 1); wpm(hp, b, bytes([0xCC]))
                    armed = True; print('armed'); sys.stdout.flush()
                elif ec == 0x4000001F and addr in orig:
                    th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                    ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
                    k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
                    busy = struct.unpack('<i', rpm(hp, 0x5a291c, 4))[0]
                    turn = u32(hp, 0x5a2918)
                    if BPS[addr] == 'kill':
                        key = rpm(hp, ctx.Eax, 0x18)
                        s, tg, e = struct.unpack('<IIH', key[:10])
                        if ONLY2 and ctx.Edx != 2:
                            pass
                        else:
                          if ctx.Edx == 2:
                            pl = struct.unpack_from('<I', key, 0x14)[0]
                            print('        kill-request payload %s' % (rpm(hp, pl, 16).hex() if pl else '-'))
                            if pl:
                                tgt = u32(hp, pl); lst = u32(hp, 0x59024c); node = u32(hp, lst); n = 0; hits = []
                                while node and n < 20000:
                                    h = rpm(hp, node + 8, 0x18); sq, tg2, e2 = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]
                                    if sq == tgt:
                                        bp = struct.unpack_from('<I', h, 0x14)[0]
                                        hits.append('#%d(emp=%d gen=%d type=%d body=%s)' % (n, e2, tg2, ty, rpm(hp, bp, 8).hex() if bp else ''))
                                    node = u32(hp, node); n += 1
                                print('        list size %d, orders with seqno %d: %s' % (n, tgt, ' '.join(hits) or 'NONE'))
                                node = u32(hp, lst); near = []
                                while node:
                                    h = rpm(hp, node + 8, 0x18); sq, tg2, e2 = struct.unpack('<IIH', h[:10]); ty = struct.unpack_from('<i', h, 0x10)[0]
                                    near.append((sq - tgt if sq >= tgt else -(tgt - sq), e2, ty, tg2))
                                    node = u32(hp, node)
                                near.sort(key=lambda x: abs(x[0]))
                                print('        nearest live seqnos (delta,emp,type,gen): %s' % near[:6])
                          print('%7.3f turn %d busy %d KILL mode %d key seq=%d gen=%d emp=%d  stack %s' % (time.time() - t0, turn, busy, ctx.Edx, s, tg, e, stack(hp, ctx.Esp)))
                    elif not ONLY2 or BPS[addr] == 'found2':
                        o = u32(hp, ctx.Esp + 0x19c)
                        if o:
                            h = rpm(hp, o, 0x18); s, tg, e = struct.unpack('<IIH', h[:10]); typ = struct.unpack_from('<i', h, 0x10)[0]
                            p = struct.unpack_from('<I', h, 0x14)[0]; body = rpm(hp, p, 8).hex() if p else ''
                            print('        -> matched order seq=%d gen=%d emp=%d type=%d body=%s' % (s, tg, e, typ, body))
                        else:
                            print('        -> no match')
                    sys.stdout.flush()
                    wpm(hp, addr, orig[addr]); ctx.Eip = addr; ctx.EFlags |= 0x100
                    k32.Wow64SetThreadContext(th, ctypes.byref(ctx)); k32.CloseHandle(th); pend[ev.dwThreadId] = addr
                elif ec in (0x4000001E, 0x80000004) and ev.dwThreadId in pend:
                    wpm(hp, pend.pop(ev.dwThreadId), bytes([0xCC]))
                elif ec in (0x80000003, 0x4000001F, 0x4000001E, 0x80000004): pass
                else:
                    # any other exception (access violation, ...): log it, the game handles it or dies
                    cont = DBG_EXCEPTION_NOT_HANDLED
                    try:
                        th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                        ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
                        k32.Wow64GetThreadContext(th, ctypes.byref(ctx)); k32.CloseHandle(th)
                        info = [er.ExceptionInformation[i] for i in range(min(er.NumberParameters, 3))]
                        print('%7.3f turn %d busy %d EXCEPTION %08x at %08x %s chance info %s eip %08x eax %08x ebx %08x ecx %08x edx %08x esi %08x edi %08x esp %08x stack %s' % (
                            time.time() - t0, u32(hp, 0x5a2918), struct.unpack('<i', rpm(hp, 0x5a291c, 4))[0], ec, addr,
                            'first' if ev.u.Exception.dwFirstChance else 'SECOND', [hex(x) for x in info], ctx.Eip, ctx.Eax, ctx.Ebx,
                            ctx.Ecx, ctx.Edx, ctx.Esi, ctx.Edi, ctx.Esp, stack(hp, ctx.Esp)))
                    except Exception as e:
                        print('EXCEPTION %08x at %08x (context failed: %s)' % (ec, addr, e))
                    sys.stdout.flush()
            elif ev.dwDebugEventCode == 5:
                print('exited, exit code %#x' % (ev.u.ExitProcess.dwExitCode & 0xffffffff)); sys.stdout.flush(); return
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        for b, o in orig.items(): wpm(hp, b, o)
        t1 = time.time()
        while pend and time.time() - t1 < 5:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200): continue
            if ev.dwDebugEventCode == 1 and ev.u.Exception.ExceptionRecord.ExceptionCode in (0x4000001E, 0x80000004):
                pend.pop(ev.dwThreadId, None)
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
        k32.DebugActiveProcessStop(pid); print('detached')

if __name__ == '__main__': main()
