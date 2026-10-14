"""Report which trek.exe variants have non-zero bytes in a candidate code cave."""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe import PE

root, lo, size = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 0)
used = []
n = 0
for f in sorted(glob.glob(os.path.join(root, '**', 'trek*.exe'), recursive=True)):
    n += 1
    b = PE(f).read(lo, size)
    nz = [i for i, x in enumerate(b) if x]
    if nz:
        used.append((os.path.basename(os.path.dirname(f)), os.path.basename(f), hex(lo + nz[0]), hex(lo + nz[-1]), len(nz)))
print('checked', n, 'variants using region:', len(used))
for u in used[:20]:
    print('  ', u)
