"""Recognises the items in the inventory's slots from the picture, against
the game's own icons.

  python icon_match.py <folder with view_*.png>    print what is in the slots

Each slot is scaled down to the game's own resolution (the client draws the
icons 2.75 times enlarged in 3840x2160, measured 2026-10-26) and compared
with every icon in icon_library.npz, on the icon's own pixels only (the
alpha channel as a mask). No hovering and no OCR are needed, and a name
that several items share (White Jeans) is settled by the picture.
"""
import glob
import os
import re
import sys

import cv2
import numpy as np

from scan_inventory import COLUMNS, DX, DY, ROWS, is_empty

HERE = os.path.dirname(os.path.abspath(__file__))
SCALE = 2.75
WINDOW = 64          # half the window around the slot's centre, in client pixels
SLOT_RGB = np.array([225, 223, 213], np.float32)   # the inventory slot's grey
BLUR = 0.7           # Gaussian blur of the templates, in the game's pixels
CAP = 70.0 ** 2      # cap on the error per pixel: the badge and the count must not dominate


def load_library(path):
    """icon_library.npz with English keys, or the Swedish keys older
    versions wrote (kats, namn, storlek, bilder)."""
    d = np.load(path)
    key = lambda en, sv: d[en] if en in d else d[sv]
    return (d["ids"], key("categories", "kats"), key("names", "namn"),
            key("sizes", "storlek"), key("images", "bilder"))


class IconLibrary:
    def __init__(self, path=os.path.join(HERE, "icon_library.npz")):
        self.ids, self.categories, self.names, sizes, images = load_library(path)
        # Items with pixel-identical icons (White and Blue Label Ring, 44
        # groups on 2026-11-02) can't be told apart from the picture. Only the
        # group's first is compared; twins[i] is the whole group, and the
        # caller chooses among them.
        first, self.twins, self.representative = {}, {}, []
        for i, (b, s) in enumerate(zip(images, sizes)):
            r = first.setdefault(b.tobytes() + s.tobytes(), i)
            self.twins.setdefault(r, []).append(i)
            self.representative.append(r)
        self.templates = []
        for b, (w, h) in zip(images, sizes):
            # The client scales the icons up with smoothing, so the outlines in
            # the inventory are soft. The template is blurred as much; with
            # sharp outlines the edges gave larger errors than the difference
            # between items.
            a = b[:h, :w].astype(np.float32)
            rgb = a[..., :3] * (a[..., 3:] / 255) + SLOT_RGB * (1 - a[..., 3:] / 255)
            rgb = cv2.GaussianBlur(rgb, (0, 0), BLUR)
            mask = cv2.GaussianBlur((a[..., 3] > 128).astype(np.float32), (0, 0), BLUR)
            mask = (mask > 0.15).astype(np.float32)
            self.templates.append((rgb, cv2.merge([mask, mask, mask])))

    def recognise(self, window, candidates=None, top=30):
        """window: an RGB picture around a slot, already scaled down to the
        game's resolution. Returns [(mean error, index)] sorted, best first.

        Two steps. First only the template's own pixels are compared, which
        finds the position and the 30 likeliest. That step alone prefers
        sparse templates (a few sparkles fit almost anywhere on a light slot),
        and got 16 of 114 white items wrong. So step two decides: the
        candidate is laid on a slot in the inventory's grey at its best
        position, and the WHOLE centre of the slot is compared. Pixels the
        template doesn't explain then count as well."""
        f = window.astype(np.float32)
        step1 = []
        for i in (candidates if candidates is not None else self.twins):
            rgb, mask = self.templates[i]
            if rgb.shape[0] > f.shape[0] or rgb.shape[1] > f.shape[1]:
                continue
            res = cv2.matchTemplate(f, rgb, cv2.TM_SQDIFF, mask=mask)
            res[~np.isfinite(res)] = np.inf
            _, _, pos, _ = cv2.minMaxLoc(res)
            step1.append((float(res.min()) / max(1.0, mask.sum()), i, pos))
        step1.sort()
        h, w = f.shape[:2]
        y0, y1, x0, x1 = int(h * 0.15), int(h * 0.85), int(w * 0.15), int(w * 0.85)
        part = f[y0:y1, x0:x1]
        # The Cash badge (a red-orange "C" bottom right) is the same in every
        # slot and says nothing about the item; its pixels don't count.
        badge = (part[..., 0] > 170) & (part[..., 1] < 110) & (part[..., 2] < 90)
        # The game's orange-yellow frame around the last clicked slot lies on
        # the slot's edge and doesn't count either; only there, so yellow
        # items keep their pixels. With the frame, Brown Dress Shoes became
        # uncertain (ratio 1.02 to Kerning Engineering School Shoes, 2026-11-02).
        yy, xx = np.mgrid[y0:y1, x0:x1]
        edge = np.maximum(abs(yy - h / 2), abs(xx - w / 2)) >= 13
        frame = edge & (part[..., 0] > 200) & (part[..., 1] > 140) & (part[..., 1] < 225) & (part[..., 2] < 125)
        weight = (~(badge | frame)).astype(np.float32)
        out = []
        for _, i, (lx, ly) in step1[:top]:
            rgb, mask = self.templates[i]
            laid = np.empty_like(f)
            laid[:] = SLOT_RGB
            mh, mw = rgb.shape[:2]
            area = laid[ly:ly + mh, lx:lx + mw]
            area[:] = area * (1 - mask) + rgb * mask
            error = np.minimum(((laid[y0:y1, x0:x1] - part) ** 2).sum(-1) / 3, CAP)
            out.append((float((error * weight).sum() / max(1.0, weight.sum())), i))
        out.sort()
        return out


def recognise_group(lib, windows, top=30):
    """The same item in several slots: the errors are added up over the slots
    and the item that fits best overall wins. A single slot can otherwise go
    wrong (one of two Bunny Earmuffs became Transparent Hat, 2026-10-26).
    Returns (index, mean error, ratio to the second best)."""
    rankings = [dict((i, e) for e, i in lib.recognise(f, top=top)) for f in windows]
    everyone = set().union(*rankings)
    total = {}
    for i in everyone:
        # A candidate missing from a slot's top list counts that slot's worst error.
        total[i] = sum(r.get(i, max(r.values())) for r in rankings) / len(rankings)
    order = sorted(everyone, key=total.get)
    best = order[0]
    ratio = total[order[1]] / max(1.0, total[best]) if len(order) > 1 else 9.9
    return best, total[best], ratio


def slot_window(view_rgb, r, c):
    """The window around slot (r, c) in a view, scaled down to the game's
    resolution.

    At the view's edge the window is padded with the slot's grey instead of
    being cut, so that the slot always sits in the middle. Cut, the slots in
    a view's top row sat off-centre, and step two in recognise compares the
    window's centre: on 2026-11-02 Yellow Spatula (row 18, at the top of
    view 18) became Yellow Cowboy Hat."""
    cx, cy = 52 + DX * c, 44 + DY * r
    h, w = view_rgb.shape[:2]
    part = view_rgb[max(0, cy - WINDOW):min(h, cy + WINDOW), max(0, cx - WINDOW):min(w, cx + WINDOW)]
    up, left = max(0, WINDOW - cy), max(0, WINDOW - cx)
    down, right = max(0, cy + WINDOW - h), max(0, cx + WINDOW - w)
    if up or left or down or right:
        part = cv2.copyMakeBorder(np.ascontiguousarray(part), up, down, left, right,
                                  cv2.BORDER_CONSTANT, value=SLOT_RGB.tolist())
    return cv2.resize(part, None, fx=1 / SCALE, fy=1 / SCALE, interpolation=cv2.INTER_AREA)


def views(folder):
    """{inventory row at the top of the view: path} for view_NN.png in folder
    (vy_NN.png from older versions too)."""
    return {int(re.findall(r"\d+", os.path.basename(f))[0]): f
            for pattern in ("vy_[0-9]*.png", "view_[0-9]*.png")
            for f in glob.glob(os.path.join(folder, pattern))}


def slots(folder):
    """[(inventory row, column, window)] for every filled slot, once each."""
    from PIL import Image
    v = views(folder)
    out = []
    for g in range(max(v) + ROWS):
        k = max(t for t in v if t <= g)
        img = Image.open(v[k])
        rgb = np.asarray(img.convert("RGB"))
        for c in range(COLUMNS):
            if not is_empty(img, g - k, c):
                out.append((g, c, slot_window(rgb, g - k, c)))
    return out


def main(folder):
    sys.stdout.reconfigure(encoding="utf-8")
    lib = IconLibrary()
    for g, c, f in slots(folder):
        (error, i), (error2, _) = lib.recognise(f)[:2]
        print("row %2d col %d  %-28s %s  error %6.1f  second best %6.1f"
              % (g, c, lib.names[i], lib.ids[i], error, error2))


if __name__ == "__main__":
    main(sys.argv[1])
