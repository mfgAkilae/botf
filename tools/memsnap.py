"""Snapshot / diff writable memory of one instance.
usage: memsnap.py <inst> save <file> | diff <file> [maxreport]"""
import ctypes, os, pickle, struct, sys
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p), ('AllocationProtect', wintypes.DWORD),
                ('PartitionId', wintypes.WORD), ('RegionSize', ctypes.c_size_t), ('State', wintypes.DWORD), ('Protect', wintypes.DWORD), ('Type', wintypes.DWORD)]
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.OpenProcess.restype = wintypes.HANDLE
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

def snap(pid):
    h = k32.OpenProcess(0x0410, False, pid)
    out = {}; a = 0; m = MBI()
    while a < 0x7fff0000 and k32.VirtualQueryEx(h, a, ctypes.byref(m), ctypes.sizeof(m)):
        base = m.BaseAddress or 0; size = m.RegionSize
        if m.State == 0x1000 and m.Protect in (0x04, 0x40, 0x08) and m.Type in (0x20000, 0x1000000) and size < 0x4000000:
            buf = ctypes.create_string_buffer(size); got = ctypes.c_size_t()
            if k32.ReadProcessMemory(h, base, buf, size, ctypes.byref(got)):
                out[base] = buf.raw[:got.value]
        a = base + size
    k32.CloseHandle(h)
    return out

if __name__ != "__main__":
    pass
else:
  inst, cmd, f = sys.argv[1], sys.argv[2], sys.argv[3]
  pid = H.load_state()[inst]
  s = snap(pid)
  if cmd == 'save':
      pickle.dump(s, open(f, 'wb')); print('saved', len(s), 'regions', sum(map(len, s.values())) // 1024, 'KB')
  else:
      old = pickle.load(open(f, 'rb')); mx = int(sys.argv[4]) if len(sys.argv) > 4 else 60
      n = 0
      for base, b in sorted(s.items()):
          o = old.get(base)
          if o is None or len(o) != len(b):
              continue
          i = 0
          while i < len(b):
              if b[i] != o[i]:
                  j = i
                  while j < len(b) and (b[j] != o[j] or (j + 4 < len(b) and b[j:j+4] != o[j:j+4])):
                      j += 1
                  if n < mx:
                      print('%08x +%d old %s new %s' % (base + i, j - i, o[i:min(j, i + 24)].hex(), b[i:min(j, i + 24)].hex()))
                  n += 1; i = j
              else:
                  i += 1
      print('changed runs', n)
