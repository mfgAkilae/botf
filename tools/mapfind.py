"""Find the player's own fleet icons (race emblem) on the galaxy map screenshot.
usage: mapfind.py <screenshot.png> <emblem.png>   prints the icon centres (game coordinates)"""
import sys
import numpy as np
from PIL import Image

MAP = (245, 40, 780, 425)          # galaxy map area of the 800x600 screen (excludes the side panels)


def find(img, tpl, thresh=18.0, step=1, m=3):
    """centres of the template in img (both PIL RGB) inside MAP; mean abs difference of the inner part"""
    a = np.asarray(img.convert('RGB'), dtype=np.int16)
    t = np.asarray(tpl.convert('RGB'), dtype=np.int16)
    th, tw = t.shape[:2]
    # m: ignore the template border (background shows through)
    t = t[m:th - m, m:tw - m]
    x0, y0, x1, y1 = MAP
    hits = []
    sub = a[y0:y1, x0:x1]
    H, W = sub.shape[:2]
    best = {}
    for dy in range(0, H - (th - 2 * m), step):
        row = sub[dy:dy + th - 2 * m]
        for dx in range(0, W - (tw - 2 * m), step):
            d = np.abs(row[:, dx:dx + tw - 2 * m] - t).mean()
            if d < thresh:
                hits.append((d, x0 + dx + tw // 2 - m, y0 + dy + th // 2 - m))
    hits.sort()
    out = []
    for d, x, y in hits:                                    # non-maximum suppression
        if all(abs(x - u) > 15 or abs(y - v) > 15 for _, u, v in out):
            out.append((d, x, y))
    return [(x, y) for _, x, y in out]


if __name__ == '__main__':
    print(find(Image.open(sys.argv[1]), Image.open(sys.argv[2])))
