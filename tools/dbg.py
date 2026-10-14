"""Minimal Win32 debugger for 32-bit trek.exe (run from 64-bit Python via WOW64 debugging).
Logs DLL loads, exceptions (first chance), OutputDebugString, thread/process exit.
usage: dbg.py <exe> <cwd> [timeout_s] [break_va_hex ...]
"""
import ctypes, sys, time
from ctypes import wintypes

k32 = ctypes.WinDLL('kernel32', use_last_error=True)

DEBUG_ONLY_THIS_PROCESS = 2
CREATE_NEW_CONSOLE = 0x10
DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001

class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR), ('lpDesktop', wintypes.LPWSTR),
                ('lpTitle', wintypes.LPWSTR), ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
                ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD), ('dwXCountChars', wintypes.DWORD),
                ('dwYCountChars', wintypes.DWORD), ('dwFillAttribute', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD), ('lpReserved2', ctypes.c_void_p),
                ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE), ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]

class EXCEPTION_RECORD(ctypes.Structure):
    pass
EXCEPTION_RECORD._fields_ = [('ExceptionCode', wintypes.DWORD), ('ExceptionFlags', wintypes.DWORD),
                             ('ExceptionRecord', ctypes.c_void_p), ('ExceptionAddress', ctypes.c_void_p),
                             ('NumberParameters', wintypes.DWORD), ('ExceptionInformation', ctypes.c_size_t * 15)]

class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('ExceptionRecord', EXCEPTION_RECORD), ('dwFirstChance', wintypes.DWORD)]

class LOAD_DLL_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('hFile', wintypes.HANDLE), ('lpBaseOfDll', ctypes.c_void_p), ('dwDebugInfoFileOffset', wintypes.DWORD),
                ('nDebugInfoSize', wintypes.DWORD), ('lpImageName', ctypes.c_void_p), ('fUnicode', wintypes.WORD)]

class EXIT_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('dwExitCode', wintypes.DWORD)]

class OUTPUT_DEBUG_STRING_INFO(ctypes.Structure):
    _fields_ = [('lpDebugStringData', ctypes.c_void_p), ('fUnicode', wintypes.WORD), ('nDebugStringLength', wintypes.WORD)]

class U(ctypes.Union):
    _fields_ = [('Exception', EXCEPTION_DEBUG_INFO), ('LoadDll', LOAD_DLL_DEBUG_INFO), ('ExitProcess', EXIT_PROCESS_DEBUG_INFO),
                ('DebugString', OUTPUT_DEBUG_STRING_INFO), ('raw', ctypes.c_byte * 160)]

class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [('dwDebugEventCode', wintypes.DWORD), ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD), ('u', U)]

k32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION)]
k32.WaitForDebugEvent.argtypes = [ctypes.POINTER(DEBUG_EVENT), wintypes.DWORD]
k32.ContinueDebugEvent.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]


def rpm(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
    return buf.raw[:got.value]


class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [('ContextFlags', wintypes.DWORD), ('Dr', wintypes.DWORD * 6), ('FloatSave', ctypes.c_byte * 112),
                ('SegGs', wintypes.DWORD), ('SegFs', wintypes.DWORD), ('SegEs', wintypes.DWORD), ('SegDs', wintypes.DWORD),
                ('Edi', wintypes.DWORD), ('Esi', wintypes.DWORD), ('Ebx', wintypes.DWORD), ('Edx', wintypes.DWORD),
                ('Ecx', wintypes.DWORD), ('Eax', wintypes.DWORD), ('Ebp', wintypes.DWORD), ('Eip', wintypes.DWORD),
                ('SegCs', wintypes.DWORD), ('EFlags', wintypes.DWORD), ('Esp', wintypes.DWORD), ('SegSs', wintypes.DWORD),
                ('Ext', ctypes.c_byte * 512)]

k32.Wow64GetThreadContext.argtypes = [wintypes.HANDLE, ctypes.POINTER(WOW64_CONTEXT)]
k32.Wow64SetThreadContext.argtypes = [wintypes.HANDLE, ctypes.POINTER(WOW64_CONTEXT)]
k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.OpenThread.restype = wintypes.HANDLE
k32.FlushInstructionCache.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t]


def wpm(h, addr, data):
    n = ctypes.c_size_t()
    k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n))
    k32.FlushInstructionCache(h, ctypes.c_void_p(addr), len(data))


def main():
    exe, cwd = sys.argv[1], sys.argv[2]
    timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 30
    bps = [int(x, 16) for x in sys.argv[4:]]
    orig = {}
    import os
    env = dict(os.environ); env['__COMPAT_LAYER'] = os.environ.get('BOTF_COMPAT', 'DWM8And16BitMitigation HighDpiAware')
    NUL = chr(0)
    envblk = ctypes.create_unicode_buffer(''.join('%s=%s' % kv + NUL for kv in env.items()) + NUL)
    si = STARTUPINFO(); si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()
    cmd = ctypes.create_unicode_buffer('"%s"' % exe)
    if not k32.CreateProcessW(exe, cmd, None, None, False, DEBUG_ONLY_THIS_PROCESS | 0x400, envblk, cwd, ctypes.byref(si), ctypes.byref(pi)):
        raise OSError(ctypes.get_last_error())
    t0 = time.time()
    ev = DEBUG_EVENT()
    nexc = 0
    while time.time() - t0 < timeout:
        if not k32.WaitForDebugEvent(ctypes.byref(ev), 500):
            continue
        code = ev.dwDebugEventCode
        cont = DBG_CONTINUE
        if code == 1:
            er = ev.u.Exception.ExceptionRecord
            first = ev.u.Exception.dwFirstChance
            ec = er.ExceptionCode
            addr = er.ExceptionAddress or 0
            if ec not in (0x80000003, 0x4000001F, 0x406D1388) or nexc < 3:
                info = [er.ExceptionInformation[i] for i in range(min(er.NumberParameters, 4))]
                print('EXC %08x at %08x first=%d info=%s' % (ec, addr, first, [hex(x) for x in info]))
            nexc += 1
            if ec == 0x4000001F and addr in orig:
                th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
                k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
                st = rpm(pi.hProcess, ctx.Esp, 128)
                import struct
                words = struct.unpack('<32I', st.ljust(128, bytes(1)))
                print('BP %08x eax=%08x ebx=%08x ecx=%08x edx=%08x esi=%08x edi=%08x ebp=%08x esp=%08x' % (addr, ctx.Eax, ctx.Ebx, ctx.Ecx, ctx.Edx, ctx.Esi, ctx.Edi, ctx.Ebp, ctx.Esp))
                print('   stack', ' '.join('%08x' % w for w in words))
                try:
                    class TBI(ctypes.Structure):
                        _fields_ = [('ExitStatus', ctypes.c_long), ('TebBaseAddress', ctypes.c_void_p), ('cid', ctypes.c_void_p * 2),
                                    ('AffinityMask', ctypes.c_void_p), ('Priority', ctypes.c_long), ('BasePriority', ctypes.c_long)]
                    tbi = TBI()
                    ctypes.WinDLL('ntdll').NtQueryInformationThread(th, 0, ctypes.byref(tbi), ctypes.sizeof(tbi), None)
                    teb32 = (tbi.TebBaseAddress or 0) + 0x2000
                    le = struct.unpack('<I', rpm(pi.hProcess, teb32 + 0x34, 4))[0]
                    print('   LastError(32) = %d (0x%x)' % (le, le))
                except Exception as ex:
                    print('   lasterror read failed', ex)
                wpm(pi.hProcess, addr, orig.pop(addr))
                ctx.Eip = addr
                k32.Wow64SetThreadContext(th, ctypes.byref(ctx))
                k32.CloseHandle(th)
                cont = DBG_CONTINUE
            elif ec in (0x80000003, 0x4000001F):
                if bps and not orig and ec == 0x4000001F:
                    for b in bps:
                        orig[b] = rpm(pi.hProcess, b, 1)
                        wpm(pi.hProcess, b, bytes([0xCC]))
                    print('breakpoints set', [hex(b) for b in bps])
                cont = DBG_CONTINUE
            else:
                cont = DBG_EXCEPTION_NOT_HANDLED
        elif code == 6:
            ld = ev.u.LoadDll
            name = ''
            if ld.hFile:
                b = ctypes.create_unicode_buffer(520)
                k32.GetFinalPathNameByHandleW(ld.hFile, b, 520, 0)
                name = b.value
                k32.CloseHandle(ld.hFile)
            print('DLL %08x %s' % (ld.lpBaseOfDll or 0, name))
        elif code == 8:
            ds = ev.u.DebugString
            s = rpm(pi.hProcess, ds.lpDebugStringData, ds.nDebugStringLength)
            print('ODS', s.decode('latin1', 'replace').rstrip())
        elif code == 5:
            print('EXIT code %08x after %.1fs' % (ev.u.ExitProcess.dwExitCode, time.time() - t0))
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
            return
        elif code == 3:
            print('CREATE_PROCESS')
        k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    print('timeout; process still running pid', pi.dwProcessId)
    k32.DebugActiveProcessStop(pi.dwProcessId)


if __name__ == '__main__':
    main()
