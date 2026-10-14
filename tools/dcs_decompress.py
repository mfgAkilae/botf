"""Decompress WinSxS 'DCS\\x01' payload files (LZMS via Windows Compression API).
usage: dcs_decompress.py <in> <out>
"""
import ctypes, struct, sys
from ctypes import wintypes

COMPRESS_ALGORITHM_LZMS = 5
COMPRESS_RAW = 1 << 29

cab = ctypes.WinDLL('cabinet.dll')
cab.CreateDecompressor.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
cab.CreateDecompressor.restype = wintypes.BOOL
cab.Decompress.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
cab.Decompress.restype = wintypes.BOOL
cab.CloseDecompressor.argtypes = [ctypes.c_void_p]


def decompress(data, out_size, raw):
    h = ctypes.c_void_p()
    alg = COMPRESS_ALGORITHM_LZMS | (COMPRESS_RAW if raw else 0)
    if not cab.CreateDecompressor(alg, None, ctypes.byref(h)):
        raise OSError(ctypes.get_last_error())
    try:
        out = ctypes.create_string_buffer(out_size)
        got = ctypes.c_size_t(0)
        inbuf = ctypes.create_string_buffer(data, len(data))
        ok = cab.Decompress(h, inbuf, len(data), out, out_size, ctypes.byref(got))
        if not ok:
            return None
        return out.raw[:got.value]
    finally:
        cab.CloseDecompressor(h)


src = open(sys.argv[1], 'rb').read()
assert src[:4] == b'DCS\x01', src[:4]
# Layout seen in WinSxS payloads: 'DCS\x01' u32 nchunks u32 total_size, then per chunk:
# u32 chunk_len, then chunk_len bytes = u32 chunk_uncompressed + raw LZMS stream.
nchunks, total = struct.unpack_from('<II', src, 4)
pos = 12
outp = b''
for _ in range(nchunks):
    clen = struct.unpack_from('<I', src, pos)[0]
    usz = struct.unpack_from('<I', src, pos + 4)[0]
    res = decompress(src[pos + 8:pos + 4 + clen], usz, True)
    if res is None:
        break
    outp += res
    pos += 4 + clen
if len(outp) == total and outp[:2] == b'MZ':
    open(sys.argv[2], 'wb').write(outp)
    print('ok chunks=%d size=%d' % (nchunks, total))
    sys.exit(0)
# Try layouts: [hdr4][ver4][size8][data] or similar
for off in (8, 16, 12):
    for raw in (True, False):
        size = None
        if off == 16:
            size = struct.unpack_from('<Q', src, 8)[0]
        elif off == 12:
            size = struct.unpack_from('<I', src, 8)[0]
        cap = size if size and 0 < size < 64 << 20 else 16 << 20
        res = decompress(src[off:], cap, raw)
        if res and res[:2] == b'MZ':
            open(sys.argv[2], 'wb').write(res)
            print('ok off=%d raw=%s size=%d' % (off, raw, len(res)))
            sys.exit(0)
print('failed')
sys.exit(1)
