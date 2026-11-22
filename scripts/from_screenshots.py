"""Reads the Deco tab from screenshots you took yourself, instead of the
script scrolling in the game (sync.py --screenshots <folder>).

For players who don't want a program to touch the game: open Item Inventory
on the Deco tab, press Print Screen, scroll down yourself, press Print Screen
again, and so on to the bottom. Each new screenshot should show at least one
row from the one before. The game saves them as Maple_YYMMDD_HHMMSS.jpg in
its own folder; the menu asks for that folder once.

What it does:
  1. takes the day's screenshots from the folder (date in the name like the
     game's, or the file's date), oldest first
  2. finds Item Inventory in each, in any resolution and shape (16:9, 16:10,
     4:3), measures how large the game drew it and scales the screenshot to
     the size the grid was measured in; keeps only those with the Deco tab
     selected, and cuts out the grid
  3. fits the screenshots together by comparing their rows, so a row that
     shows up in several screenshots counts once
  4. builds each row from all the screenshots it is in (a per-pixel median),
     so the mouse pointer or a tooltip over a slot in one screenshot goes away
  5. writes the result as views (view_NN.png) that sync.py recognises as usual

Nothing is sent to the game and no admin rights are needed.

    python from_screenshots.py <screenshot folder> <out folder> [YYYY-MM-DD]
"""
import datetime
import glob
import os
import re
import sys

import numpy as np
from PIL import Image

from scan_inventory import (COLUMNS, DECO_TAB, DX, DY, MEASURED, ROWS, SLOT, TAB_TEMPLATE,
                            TAB_TEMPLATE_POS, X0, Y0)

PICTURES = (".jpg", ".jpeg", ".png", ".bmp")
# The game draws its own mouse pointer (a white glove) into its screenshots.
# Where it is, the pixels count as unknown: the other screenshots of that row
# fill them in, or the slot's colour when there are none (a pointer over an
# empty slot). Cut out 2026-11-18 from two screenshots of the same row.
CURSOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cursor.png")
CURSOR_ERROR = 500.0    # mean squared difference per channel below which the pointer is there
MARGIN = 90             # the pointer can reach into the grid from outside it
HEIGHT = 44 + DY * (ROWS - 1) + 48          # a view's height, as scan_inventory.grid cuts it
WIDTH = 52 + DX * (COLUMNS - 1) + 52


def taken_at(path):
    """The time a screenshot was taken: from the name (the game's
    Maple_YYMMDD_HHMMSS, or YYYY-MM-DD HHMMSS like Windows), else the file's."""
    name = os.path.basename(path)
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)", name)
    if m:
        y, mo, d, h, mi, s = (int(x) for x in m.groups())
        try:
            return datetime.datetime(2000 + y, mo, d, h, mi, s)
        except ValueError:
            pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\D+(\d{2})(\d{2})(\d{2})", name)
    if m:
        try:
            return datetime.datetime(*(int(x) for x in m.groups()))
        except ValueError:
            pass
    return datetime.datetime.fromtimestamp(os.path.getmtime(path))


def days_screenshots(folder, day):
    paths = [f for f in glob.glob(os.path.join(folder, "*")) if f.lower().endswith(PICTURES)]
    timed = [(taken_at(f), f) for f in paths]
    return [f for t, f in sorted(timed) if t.date() == day]


def read_cursor():
    if not os.path.exists(CURSOR):
        return None
    rgba = np.asarray(Image.open(CURSOR).convert("RGBA"), dtype=np.float32)
    mask = (rgba[..., 3] > 127).astype(np.float32)
    return rgba[..., :3], np.repeat(mask[..., None], 3, axis=2)


def cursor_pixels(img, x0, y0, cursor):
    """Where the game's pointer covers the grid, as a mask the size of a view
    (True = unknown), or None when it isn't over the grid."""
    import cv2
    if cursor is None:
        return None
    rgb, mask = cursor
    vx, vy = x0 - 52, y0 - 44
    area = np.asarray(img.crop((vx - MARGIN, vy - MARGIN, vx + WIDTH + MARGIN, vy + HEIGHT + MARGIN)),
                      dtype=np.float32)
    res = cv2.matchTemplate(area, rgb, cv2.TM_SQDIFF, mask=mask)
    res[~np.isfinite(res)] = np.inf
    _, _, (lx, ly), _ = cv2.minMaxLoc(res)
    if res[ly, lx] / max(1.0, mask.sum()) > CURSOR_ERROR:
        return None
    unknown = np.zeros((HEIGHT + 2 * MARGIN, WIDTH + 2 * MARGIN), bool)
    unknown[ly:ly + mask.shape[0], lx:lx + mask.shape[1]] = mask[..., 0] > 0
    unknown = cv2.dilate(unknown.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    unknown = unknown[MARGIN:MARGIN + HEIGHT, MARGIN:MARGIN + WIDTH]
    return unknown if unknown.any() else None


_SCALES = {}    # (width, height) -> the interface's size, measured once per resolution


def ui_scale(whole, template):
    """How large the game drew its interface in this screenshot, relative to
    where the grid was measured (3840x2160, where the game draws it 2.75
    times its own size), found by trying tab_template.png in many sizes.

    The size follows the window's height, not its width, and never goes below
    the game's own size: on 2026-11-22 a slot was 100 px apart at 3840x2160,
    56 at 1920x1200 (16:10) and 37 at 1280x720, 1024x768 and 800x600. Scaling
    every screenshot to 3840 px wide, as before, only fitted 16:9 from 1366x768
    up. Returns (scale, match)."""
    import cv2
    h, w = whole.shape[:2]
    # Coarse, on half the screenshot: from the game's own size (0.36) up to
    # what the height allows.
    small = cv2.resize(whole, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    best = (-1.0, None)
    for r in np.arange(0.30, h / MEASURED[1] * 1.15 + 0.05, 0.02):
        t = cv2.resize(template, None, fx=r / 2, fy=r / 2, interpolation=cv2.INTER_AREA)
        if t.shape[0] < 8 or t.shape[0] > small.shape[0] or t.shape[1] > small.shape[1]:
            continue
        m = cv2.minMaxLoc(cv2.matchTemplate(small, t, cv2.TM_CCOEFF_NORMED))[1]
        if m > best[0]:
            best = (m, r)
    if best[1] is None:
        return None, 0.0
    # Fine, on the whole screenshot, around the best coarse size.
    coarse, best = best[1], (-1.0, None)
    for r in np.arange(coarse - 0.024, coarse + 0.025, 0.004):
        t = cv2.resize(template, None, fx=r, fy=r, interpolation=cv2.INTER_AREA if r < 1 else cv2.INTER_CUBIC)
        if t.shape[0] > h or t.shape[1] > w:
            continue
        m = cv2.minMaxLoc(cv2.matchTemplate(whole, t, cv2.TM_CCOEFF_NORMED))[1]
        if m > best[0]:
            best = (m, r)
    return best[1], best[0]


def view_from_screenshot(path, template, cursor=None):
    """The Deco grid cut out of a screenshot (an array like a scanned view)
    and where the pointer covers it, or (None, None, why not)."""
    import cv2
    img = Image.open(path).convert("RGB")
    size = img.size
    if size not in _SCALES:
        scale, match = ui_scale(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR), template)
        # A screenshot without the inventory gives no size; try the next one
        # of that resolution.
        if scale is None or match < 0.7:
            return None, None, "no Item Inventory"
        _SCALES[size] = scale
    scale = _SCALES[size]
    if abs(scale - 1) > 0.002:
        img = img.resize((round(img.width / scale), round(img.height / scale)), Image.LANCZOS)
    whole = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    res = cv2.matchTemplate(whole, template, cv2.TM_CCOEFF_NORMED)
    _, match, _, (x, y) = cv2.minMaxLoc(res)
    if match < 0.7:
        return None, None, "no Item Inventory"
    dx, dy = x - TAB_TEMPLATE_POS[0], y - TAB_TEMPLATE_POS[1]
    a, b, c, d = DECO_TAB
    tab = np.asarray(img.crop((a + dx, b + dy, c + dx, d + dy)), dtype=np.int16)
    if ((tab[..., 0] - tab[..., 1]) > 50).mean() < 0.4:
        return None, None, "another tab than Deco"
    x0, y0 = X0 + dx, Y0 + dy
    view = img.crop((x0 - 52, y0 - 44, x0 - 52 + WIDTH, y0 - 44 + HEIGHT))
    return np.asarray(view, dtype=np.uint8), cursor_pixels(img, x0, y0, cursor), None


def grey(view):
    """The view in grey, slightly blurred: screenshots in different
    resolutions are scaled differently and have different JPEG noise, so the
    same rows differ in sharpness. Unblurred, the same rows in 10 resolutions
    differed by up to 11.0, over the limit (2026-11-22)."""
    import cv2
    g = np.asarray(Image.fromarray(view).convert("L"), dtype=np.float32)
    return cv2.GaussianBlur(g, (0, 0), 2)


# Measured 2026-11-22, blurred as in grey(): a view's best overlapping
# neighbour fits at 0.1-0.9 in one resolution (11 screenshots, 18 Nov) and at
# most 3.4 across 10 resolutions; views that don't overlap at 14.5 or more.
FITS = 8.0


def fit(a, b):
    """How b fits on a: (difference, k) where b's content lies k whole rows
    further down the list than a's. The list scrolls a whole row at a time,
    give or take a few pixels; the worst 30 % of pixel rows are left out,
    since a pointer or a tooltip may cover part of a view."""
    h = a.shape[0]
    best = (float("inf"), None)
    for k in range(-(ROWS - 1), ROWS):
        for fine in range(-4, 5):
            d = DY * k + fine
            x, y = (a[d:], b[:h - d]) if d >= 0 else (a[:h + d], b[-d:])
            per_row = np.abs(x - y).mean(axis=1)
            error = float(np.sort(per_row)[:max(1, int(len(per_row) * 0.7))].mean())
            if error < best[0]:
                best = (error, k)
    return best


def fit_together(views):
    """The row offset of every view. A view is placed against any view that
    is already placed, best fit first, until all are placed. Raises
    SystemExit when some views fit none of the others."""
    g = [grey(v) for v in views]
    placed = {0: 0}
    while len(placed) < len(views):
        best = None
        for i in range(len(views)):
            if i in placed:
                continue
            for j in placed:
                error, k = fit(g[j], g[i])
                if error < FITS and (best is None or error < best[0]):
                    best = (error, i, placed[j] + k)
        if best is None:
            outside = [i + 1 for i in range(len(views)) if i not in placed]
            raise SystemExit("screenshot(s) %s fit none of the others: scroll less between screenshots, "
                             "so that each shows at least one row from another." % outside)
        placed[best[1]] = best[2]
    least = min(placed.values())
    return [placed[i] - least for i in range(len(views))]


def build_views(views, unknowns, offsets, out):
    """Every row as the per-pixel median of all the views it is in, leaving
    out the pixels under the pointer, written as view_00.png, view_06.png ...
    like a scan. A pixel no view shows gets the slot's colour."""
    rows = max(offsets) + ROWS
    strips = {}       # inventory row -> [row strips, NaN under the pointer]
    for view, unknown, o in zip(views, unknowns, offsets):
        f = view.astype(np.float32)
        if unknown is not None:
            f[unknown] = np.nan
        for r in range(ROWS):
            strips.setdefault(o + r, []).append(f[DY * r:DY * r + DY] if r < ROWS - 1 else f[DY * r:HEIGHT])
    canvas = np.empty((DY * (rows + ROWS) + HEIGHT, WIDTH, 3), dtype=np.uint8)
    canvas[:] = SLOT
    for g, parts in strips.items():
        h = min(p.shape[0] for p in parts)
        stack = np.stack([p[:h] for p in parts])
        empty = np.isnan(stack).all(axis=0)          # no view shows the pixel
        with np.errstate(all="ignore"):
            med = np.nanmedian(stack, axis=0)
        med[empty] = np.array(SLOT, np.float32)[np.nonzero(empty)[-1]]
        canvas[DY * g:DY * g + h] = med.astype(np.uint8)
    os.makedirs(out, exist_ok=True)
    for k in range(0, rows, ROWS):
        Image.fromarray(canvas[DY * k:DY * k + HEIGHT]).save(os.path.join(out, "view_%02d.png" % k))
    return rows


def main(folder, out, day=None):
    import cv2
    day = day or datetime.date.today()
    paths = days_screenshots(folder, day)
    if not paths:
        raise SystemExit("No screenshots from %s in %s." % (day.isoformat(), folder))
    template = cv2.imread(TAB_TEMPLATE)
    cursor = read_cursor()
    views, unknowns, skipped = [], [], {}
    for f in paths:
        view, unknown, why = view_from_screenshot(f, template, cursor)
        if view is None:
            skipped[why] = skipped.get(why, 0) + 1
        else:
            views.append(view)
            unknowns.append(unknown)
    if any(u is not None for u in unknowns):
        print("  The mouse pointer is over the grid in %d of them; other screenshots fill in under it."
              % sum(u is not None for u in unknowns))
    print("  %d screenshots from %s, %d of them show the Deco tab%s." % (
        len(paths), day.isoformat(), len(views),
        "" if not skipped else " (skipped: " + ", ".join("%d %s" % (n, v) for v, n in skipped.items()) + ")"))
    if not views:
        raise SystemExit("None of the screenshots shows the Deco tab.")
    offsets = fit_together(views)
    rows = build_views(views, unknowns, offsets, out)
    print("  Fitted together: %d rows of the Deco tab." % rows)
    with open(os.path.join(out, "log.txt"), "w", encoding="utf-8") as fh:
        fh.write("from screenshots: %d rows\ndone\n" % rows)
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    day = datetime.date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else None
    main(sys.argv[1], sys.argv[2], day)
