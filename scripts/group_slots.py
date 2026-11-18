"""Groups the inventory slots by icon and counts how many of each.

  python group_slots.py <folder with view_*.png>

The icons are compared to each other (not the tooltip's text), so that the
same item in several slots ends up in one group, which sync.py then
recognises once.
"""
import sys

import numpy as np
from PIL import Image

from icon_match import views
from scan_inventory import CELL, COLUMNS, DX, DY, ROWS, is_empty

LIMIT = 20   # mean difference after fitting; different items give over 70
SLACK = 10   # the grid's step is not exactly DX/DY, so look for a fit within ±SLACK px
INNER = CELL - SLACK


def icon(view, r, c):
    a = np.asarray(view.convert("L"), dtype=np.int16)
    cx, cy = 52 + DX * c, 44 + DY * r
    return a[cy - CELL:cy + CELL, cx - CELL:cx + CELL]


def distance(a, b):
    """The smallest mean difference between the middle of a and b, shifted up
    to SLACK px each way."""
    k = a[SLACK:SLACK + 2 * INNER, SLACK:SLACK + 2 * INNER]
    return min(np.abs(k - b[dy:dy + 2 * INNER, dx:dx + 2 * INNER]).mean()
               for dy in range(2 * SLACK + 1) for dx in range(2 * SLACK + 1))


def groups(folder):
    """[{"slots": [(row, column)]}], one per icon, in the inventory's order.
    view_NN.png: the inventory's row NN is at the top of the view."""
    v = views(folder)
    found = []   # [icon, [(row, column)]]
    for g in range(max(v) + ROWS):
        k = max(t for t in v if t <= g)
        view = Image.open(v[k])
        r = g - k
        for c in range(COLUMNS):
            if is_empty(view, r, c):
                continue
            i = icon(view, r, c)
            for group in found:
                if distance(group[0], i) < LIMIT:
                    group[1].append((g, c))
                    break
            else:
                found.append([i, [(g, c)]])
    return [{"slots": slots} for _, slots in found]


def main(folder):
    sys.stdout.reconfigure(encoding="utf-8")
    gs = groups(folder)
    for g in gs:
        print("%2d  from row %2d" % (len(g["slots"]), g["slots"][0][0]))
    print(sum(len(g["slots"]) for g in gs), "items in", len(gs), "groups")


if __name__ == "__main__":
    main(sys.argv[1])
