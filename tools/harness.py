"""Test harness for driving two BotF instances without taking over the user's mouse.

Commands (state kept in harness_state.json next to this script):
  launch <name> <dir>            start <dir>\\trek.exe, remember pid under <name>
  wins <name>                    list top-level windows of the process
  shot <name> <out.png>          capture main window via PrintWindow
  click <name> <x> <y> [right]   post mouse click at client coords
  move <name> <x> <y>
  key <name> <vk_hex>            post WM_KEYDOWN/UP (e.g. 0d = Return)
  text <name> <string>           post WM_CHAR per character
  kill <name>
  mem <name> <addr_hex> <len>    hex dump of process memory
  alive <name>
"""
import ctypes, json, os, subprocess, sys, time
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: physical pixels
except Exception:
    pass

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harness_state.json')

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x204, 0x205
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x100, 0x101, 0x102
MK_LBUTTON, MK_RBUTTON = 1, 2

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(s):
    json.dump(s, open(STATE, 'w'), indent=1)


def windows_of(pid):
    out = []

    def cb(hwnd, lp):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            t = ctypes.create_unicode_buffer(256)
            c = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, t, 256)
            user32.GetClassNameW(hwnd, c, 256)
            r = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            out.append((hwnd, t.value, c.value, bool(user32.IsWindowVisible(hwnd)), r.right, r.bottom))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def main_window(pid):
    ws = [w for w in windows_of(pid) if w[3]]
    if not ws:
        raise SystemExit('no visible window for pid %d' % pid)
    ws.sort(key=lambda w: -(w[4] * w[5]))
    return ws[0][0]


def capture(hwnd, path):
    from PIL import Image
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    hdc = user32.GetDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(hwnd, mdc, 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    if not ok:
        gdi32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)

    class BIH(ctypes.Structure):
        _fields_ = [('biSize', wintypes.DWORD), ('biWidth', ctypes.c_long), ('biHeight', ctypes.c_long),
                    ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', ctypes.c_long), ('biYPelsPerMeter', ctypes.c_long),
                    ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]
    bih = BIH()
    bih.biSize = ctypes.sizeof(BIH)
    bih.biWidth, bih.biHeight, bih.biPlanes, bih.biBitCount = w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer('RGBA', (w, h), buf.raw, 'raw', 'BGRA', 0, 1).convert('RGB')
    if (w, h) != (800, 600):
        img = img.resize((800, 600))
    img.save(path)
    return w, h


def lparam(x, y):
    return (int(y) << 16) | (int(x) & 0xffff)


def game2client(hwnd, x, y):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return int(int(x) * r.right / 800), int(int(y) * r.bottom / 600)


CURSOR_BLOCK = 0x69e000


def set_cursor(pid, x, y):
    import struct
    h = kernel32.OpenProcess(0x0008 | 0x0020 | 0x0010 | 0x0400, False, pid)
    if not h:
        return False
    try:
        data = struct.pack('<III', int(x), int(y), 1)
        wr = ctypes.c_size_t()
        kernel32.WriteProcessMemory(h, ctypes.c_void_p(CURSOR_BLOCK), data, len(data), ctypes.byref(wr))
        return wr.value == len(data)
    finally:
        kernel32.CloseHandle(h)


def click(hwnd, x, y, right=False, pid=None):
    if pid:
        set_cursor(pid, x, y)
        time.sleep(0.15)
    x, y = game2client(hwnd, x, y)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam(x, y))
    time.sleep(0.05)
    if right:
        user32.PostMessageW(hwnd, WM_RBUTTONDOWN, MK_RBUTTON, lparam(x, y))
        time.sleep(0.08)
        user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, lparam(x, y))
    else:
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam(x, y))
        time.sleep(0.08)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam(x, y))


def readmem(pid, addr, n):
    h = kernel32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not h:
        raise OSError(ctypes.get_last_error())
    try:
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            raise OSError(ctypes.get_last_error())
        return buf.raw[:got.value]
    finally:
        kernel32.CloseHandle(h)


def writemem(pid, addr, data):
    h = kernel32.OpenProcess(0x0008 | 0x0020 | 0x0010, False, pid)
    if not h:
        raise OSError(ctypes.get_last_error())
    try:
        got = ctypes.c_size_t()
        if not kernel32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got)):
            raise OSError(ctypes.get_last_error())
        return got.value
    finally:
        kernel32.CloseHandle(h)


def pid_alive(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return code.value == 259


LAYOUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'window_layout.json')


def place(name, pid, wait=20):
    # put the game window where the user keeps it (tools/window_layout.json: name -> [x, y, w, h])
    try:
        lay = json.load(open(LAYOUT)).get(name)
    except (OSError, ValueError):
        lay = None
    if not lay:
        return
    t0 = time.time()
    while time.time() - t0 < wait:
        try:
            hw = main_window(pid)
        except SystemExit:
            hw = None
        if hw:
            # NOSIZE NOZORDER NOACTIVATE NOSENDCHANGING: without NOSENDCHANGING dxwnd rewrites the position
            user32.SetWindowPos(hw, 0, lay[0], lay[1], 0, 0, 0x0001 | 0x0004 | 0x0010 | 0x0400)
            return
        time.sleep(0.5)


def main(argv):
    st = load_state()
    cmd = argv[0]
    if cmd == 'launch':
        name, d = argv[1], argv[2]
        env = dict(os.environ)
        env['__COMPAT_LAYER'] = os.environ.get('BOTF_COMPAT', 'DWM8And16BitMitigation HighDpiAware')
        p = subprocess.Popen([os.path.join(d, 'trek.exe')] + argv[3:], cwd=d, env=env)
        st[name] = p.pid
        save_state(st)
        print('pid', p.pid)
        place(name, p.pid)
        return
    if cmd == 'place':
        place(argv[1], st[argv[1]], wait=2)
        return
    pid = st[argv[1]]
    if cmd == 'alive':
        print(pid_alive(pid))
    elif cmd == 'wins':
        for w in windows_of(pid):
            print(w)
    elif cmd == 'shot':
        print(capture(main_window(pid), argv[2]))
    elif cmd in ('click', 'rclick'):
        click(main_window(pid), argv[2], argv[3], right=(cmd == 'rclick'), pid=pid)
    elif cmd == 'move':
        hw = main_window(pid)
        set_cursor(pid, argv[2], argv[3])
        user32.PostMessageW(hw, WM_MOUSEMOVE, 0, lparam(*game2client(hw, argv[2], argv[3])))
    elif cmd == 'key':
        hw = main_window(pid)
        vk = int(argv[2], 16)
        user32.PostMessageW(hw, WM_KEYDOWN, vk, 1)
        time.sleep(0.05)
        user32.PostMessageW(hw, WM_KEYUP, vk, 0xC0000001)
    elif cmd == 'text':
        hw = main_window(pid)
        for ch in argv[2]:
            user32.PostMessageW(hw, WM_CHAR, ord(ch), 1)
            time.sleep(0.03)
    elif cmd == 'kill':
        subprocess.call(['taskkill', '/F', '/PID', str(pid)])
    elif cmd == 'mem':
        print(readmem(pid, int(argv[2], 16), int(argv[3], 0)).hex())
    else:
        raise SystemExit('unknown cmd')


if __name__ == '__main__':
    main(sys.argv[1:])
