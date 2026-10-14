"""Check whether netfix applies cleanly to every trek.exe found under a directory tree."""
import glob, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pe import PE
import netfix

root = sys.argv[1]
res = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(root, '**', 'trek*.exe'), recursive=True)):
    mod = os.path.basename(os.path.dirname(f))
    try:
        p = PE(f)
        netfix.apply(p)
        res[(mod, 'OK')].append(os.path.basename(f))
    except Exception as e:
        res[(mod, 'FAIL ' + str(e)[:70])].append(os.path.basename(f))
for (mod, st), files in sorted(res.items()):
    print('%-6s %-80s %d' % (mod, st, len(files)))
