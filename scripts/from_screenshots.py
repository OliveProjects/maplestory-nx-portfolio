"""Reads the Deco tab from screenshots you took yourself, instead of the
script scrolling in the game (sync.py --skarmbilder <folder>).

For players who don't want a program to touch the game: open Item Inventory
on the Deco tab, press Print Screen, scroll down yourself, press Print Screen
again, and so on to the bottom. Each new screenshot should show at least one
row from the one before. The game saves them as Maple_YYMMDD_HHMMSS.jpg in
its own folder; the menu asks for that folder once.

What it does:
  1. takes the day's screenshots from the folder (date in the name like the
     game's, or the file's date), oldest first
  2. finds Item Inventory in each (any 16:9 resolution, scaled to 3840x2160),
     keeps only those with the Deco tab selected, and cuts out the grid
  3. fits the screenshots together by comparing their rows, so a row that
     shows up in several screenshots counts once
  4. builds each row from all the screenshots it is in (a per-pixel median),
     so the mouse pointer or a tooltip over a slot in one screenshot goes away
  5. writes the result as views (vy_NN.png) that sync.py recognises as usual

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

from scan_inventory import (CELL, DECO_FLIK, DX, DY, KOLUMNER, MALL_FLIKAR, MALL_LAGE, RADER,
                            SLOT, UPPMATT, X0, Y0)

BILDER = (".jpg", ".jpeg", ".png", ".bmp")
# The game draws its own mouse pointer (a white glove) into its screenshots.
# Where it is, the pixels count as unknown: the other screenshots of that row
# fill them in, or the slot's colour when there are none (a pointer over an
# empty slot). Cut out 2026-11-18 from two screenshots of the same row.
PEKARE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cursor.png")
PEKARE_FEL = 500.0      # mean squared difference per channel below which the pointer is there
MARGINAL = 90           # the pointer can reach into the grid from outside it
HOJD = 44 + DY * (RADER - 1) + 48          # a view's height, as scan_inventory.rutnat cuts it
BREDD = 52 + DX * (KOLUMNER - 1) + 52


def bildens_tid(fil):
    """The time a screenshot was taken: from the name (the game's
    Maple_YYMMDD_HHMMSS, or YYYY-MM-DD HHMMSS like Windows), else the file's."""
    namn = os.path.basename(fil)
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)", namn)
    if m:
        y, mo, d, h, mi, s = (int(x) for x in m.groups())
        try:
            return datetime.datetime(2000 + y, mo, d, h, mi, s)
        except ValueError:
            pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\D+(\d{2})(\d{2})(\d{2})", namn)
    if m:
        try:
            return datetime.datetime(*(int(x) for x in m.groups()))
        except ValueError:
            pass
    return datetime.datetime.fromtimestamp(os.path.getmtime(fil))


def dagens_bilder(mapp, dag):
    filer = [f for f in glob.glob(os.path.join(mapp, "*")) if f.lower().endswith(BILDER)]
    med_tid = [(bildens_tid(f), f) for f in filer]
    return [f for t, f in sorted(med_tid) if t.date() == dag]


def las_pekare():
    if not os.path.exists(PEKARE):
        return None
    rgba = np.asarray(Image.open(PEKARE).convert("RGBA"), dtype=np.float32)
    mask = (rgba[..., 3] > 127).astype(np.float32)
    return rgba[..., :3], np.repeat(mask[..., None], 3, axis=2)


def pekarens_pixlar(bild, x0, y0, pekare):
    """Where the game's pointer covers the grid, as a mask the size of a view
    (True = unknown), or None when it isn't over the grid."""
    import cv2
    if pekare is None:
        return None
    rgb, mask = pekare
    vx, vy = x0 - 52, y0 - 44
    omr = np.asarray(bild.crop((vx - MARGINAL, vy - MARGINAL, vx + BREDD + MARGINAL, vy + HOJD + MARGINAL)),
                     dtype=np.float32)
    res = cv2.matchTemplate(omr, rgb, cv2.TM_SQDIFF, mask=mask)
    res[~np.isfinite(res)] = np.inf
    _, _, (lx, ly), _ = cv2.minMaxLoc(res)
    if res[ly, lx] / max(1.0, mask.sum()) > PEKARE_FEL:
        return None
    ogiltig = np.zeros((HOJD + 2 * MARGINAL, BREDD + 2 * MARGINAL), bool)
    ogiltig[ly:ly + mask.shape[0], lx:lx + mask.shape[1]] = mask[..., 0] > 0
    ogiltig = cv2.dilate(ogiltig.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    ogiltig = ogiltig[MARGINAL:MARGINAL + HOJD, MARGINAL:MARGINAL + BREDD]
    return ogiltig if ogiltig.any() else None


def vy_ur_bild(fil, mall, pekare=None):
    """The Deco grid cut out of a screenshot (an array like a scanned view)
    and where the pointer covers it, or (None, None, why not)."""
    import cv2
    bild = Image.open(fil).convert("RGB")
    if bild.width != UPPMATT[0]:
        bild = bild.resize((UPPMATT[0], round(bild.height * UPPMATT[0] / bild.width)), Image.LANCZOS)
    hel = cv2.cvtColor(np.asarray(bild), cv2.COLOR_RGB2BGR)
    res = cv2.matchTemplate(hel, mall, cv2.TM_CCOEFF_NORMED)
    _, traff, _, (x, y) = cv2.minMaxLoc(res)
    if traff < 0.7:
        return None, None, "no Item Inventory"
    dx, dy = x - MALL_LAGE[0], y - MALL_LAGE[1]
    a, b, c, d = DECO_FLIK
    flik = np.asarray(bild.crop((a + dx, b + dy, c + dx, d + dy)), dtype=np.int16)
    if ((flik[..., 0] - flik[..., 1]) > 50).mean() < 0.4:
        return None, None, "another tab than Deco"
    x0, y0 = X0 + dx, Y0 + dy
    vy = bild.crop((x0 - 52, y0 - 44, x0 - 52 + BREDD, y0 - 44 + HOJD))
    return np.asarray(vy, dtype=np.uint8), pekarens_pixlar(bild, x0, y0, pekare), None


def gra(vy):
    return np.asarray(Image.fromarray(vy).convert("L"), dtype=np.float32)


# Measured 2026-11-18 on 11 screenshots: views that overlap fit with a mean
# grey difference of 0-6, views that don't of 17 or more.
PASSAR = 10.0


def passning(a, b):
    """How b fits on a: (difference, k) where b's content lies k whole rows
    further down the list than a's. The list scrolls a whole row at a time,
    give or take a few pixels; the worst 30 % of pixel rows are left out,
    since a pointer or a tooltip may cover part of a view."""
    h = a.shape[0]
    basta = (float("inf"), None)
    for k in range(-(RADER - 1), RADER):
        for fin in range(-4, 5):
            d = DY * k + fin
            x, y = (a[d:], b[:h - d]) if d >= 0 else (a[:h + d], b[-d:])
            per_rad = np.abs(x - y).mean(axis=1)
            fel = float(np.sort(per_rad)[:max(1, int(len(per_rad) * 0.7))].mean())
            if fel < basta[0]:
                basta = (fel, k)
    return basta


def passa_ihop(vyer):
    """The row offset of every view. A view is placed against any view that
    is already placed, best fit first, until all are placed. Raises
    SystemExit when some views fit none of the others."""
    g = [gra(v) for v in vyer]
    lage = {0: 0}
    while len(lage) < len(vyer):
        basta = None
        for i in range(len(vyer)):
            if i in lage:
                continue
            for j in lage:
                fel, k = passning(g[j], g[i])
                if fel < PASSAR and (basta is None or fel < basta[0]):
                    basta = (fel, i, lage[j] + k)
        if basta is None:
            utanfor = [i + 1 for i in range(len(vyer)) if i not in lage]
            raise SystemExit("screenshot(s) %s fit none of the others: scroll less between screenshots, "
                             "so that each shows at least one row from another." % utanfor)
        lage[basta[1]] = basta[2]
    minst = min(lage.values())
    return [lage[i] - minst for i in range(len(vyer))]


def bygg_vyer(vyer, ogiltiga, lage, ut):
    """Every row as the per-pixel median of all the views it is in, leaving
    out the pixels under the pointer, written as vy_00.png, vy_06.png ...
    like a scan. A pixel no view shows gets the slot's colour."""
    rader = max(lage) + RADER
    band = {}       # inventory row -> [row strips, NaN under the pointer]
    for vy, ogiltig, l in zip(vyer, ogiltiga, lage):
        f = vy.astype(np.float32)
        if ogiltig is not None:
            f[ogiltig] = np.nan
        for r in range(RADER):
            band.setdefault(l + r, []).append(f[DY * r:DY * r + DY] if r < RADER - 1 else f[DY * r:HOJD])
    duk = np.empty((DY * (rader + RADER) + HOJD, BREDD, 3), dtype=np.uint8)
    duk[:] = SLOT
    for g, remsor in band.items():
        h = min(r.shape[0] for r in remsor)
        stack = np.stack([r[:h] for r in remsor])
        tom = np.isnan(stack).all(axis=0)          # no view shows the pixel
        with np.errstate(all="ignore"):
            med = np.nanmedian(stack, axis=0)
        med[tom] = np.array(SLOT, np.float32)[np.nonzero(tom)[-1]]
        duk[DY * g:DY * g + h] = med.astype(np.uint8)
    os.makedirs(ut, exist_ok=True)
    for k in range(0, rader, RADER):
        Image.fromarray(duk[DY * k:DY * k + HOJD]).save(os.path.join(ut, "vy_%02d.png" % k))
    return rader


def main(mapp, ut, dag=None):
    import cv2
    dag = dag or datetime.date.today()
    filer = dagens_bilder(mapp, dag)
    if not filer:
        raise SystemExit("No screenshots from %s in %s." % (dag.isoformat(), mapp))
    mall = cv2.imread(MALL_FLIKAR)
    pekare = las_pekare()
    vyer, ogiltiga, hoppade = [], [], {}
    for f in filer:
        vy, ogiltig, varfor = vy_ur_bild(f, mall, pekare)
        if vy is None:
            hoppade[varfor] = hoppade.get(varfor, 0) + 1
        else:
            vyer.append(vy)
            ogiltiga.append(ogiltig)
    if any(o is not None for o in ogiltiga):
        print("  The mouse pointer is over the grid in %d of them; other screenshots fill in under it."
              % sum(o is not None for o in ogiltiga))
    print("  %d screenshots from %s, %d of them show the Deco tab%s." % (
        len(filer), dag.isoformat(), len(vyer),
        "" if not hoppade else " (skipped: " + ", ".join("%d %s" % (n, v) for v, n in hoppade.items()) + ")"))
    if not vyer:
        raise SystemExit("None of the screenshots shows the Deco tab.")
    lage = passa_ihop(vyer)
    rader = bygg_vyer(vyer, ogiltiga, lage, ut)
    print("  Fitted together: %d rows of the Deco tab." % rader)
    with open(os.path.join(ut, "logg.txt"), "w", encoding="utf-8") as fh:
        fh.write("from screenshots: %d rows\ndone\n" % rader)
    return rader


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    dag = datetime.date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else None
    main(sys.argv[1], sys.argv[2], dag)
