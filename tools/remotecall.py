"""Test helper: run a parameterless game function in a new thread of one test instance (CreateRemoteThread).
Only for functions that are safe on another thread, e.g. FUN_0050d320 (host broadcasts options message 0x85).
usage: remotecall.py <inst> <addr_hex>"""
import ctypes, os, sys
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.CreateRemoteThread.restype = wintypes.HANDLE
k32.CreateRemoteThread.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
                                   wintypes.DWORD, ctypes.c_void_p]
inst, addr = sys.argv[1], int(sys.argv[2], 16)
h = k32.OpenProcess(0x1F0FFF, False, H.load_state()[inst])
t = k32.CreateRemoteThread(h, None, 0, ctypes.c_void_p(addr), None, 0, None)
if not t:
    raise OSError(ctypes.get_last_error())
print('wait', k32.WaitForSingleObject(t, 10000))
