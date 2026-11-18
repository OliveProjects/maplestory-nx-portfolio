"""Builds a library with the icon of every cash item from the client's WZ files.

  python icon_library.py

Writes icon_library.npz next to the script: id, category, name and the icon
(iconRaw, RGBA, pasted top left in a 40x40 square). icon_match.py recognises
the inventory's slots against it. Build it again after a game update.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

import settings as cfg
from wz.img_parser import decode_canvas
from wz.wz_archive import WzArchive

DATA = cfg.WZ_DATA
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icon_library.npz")
# Categories that can be in the Deco tab. Faces, hair, afterimages and
# mounts are never items there.
CATEGORIES = ["Accessory", "Cap", "Cape", "Coat", "Glove", "Longcoat", "Pants",
              "PetEquip", "Ring", "Shield", "Shoes", "Weapon"]
SQUARE = 40

_archives = {}
_imgs = {}


def read_img(img_path):
    """'Character/Cap/_Canvas/01002000.img' -> the parsed tree, from the right archive."""
    if img_path in _imgs:
        return _imgs[img_path]
    folder, name = img_path.rsplit("/", 1)
    base = os.path.join(DATA, *folder.split("/"))
    for path in sorted(glob.glob(os.path.join(base, os.path.basename(base) + "_[0-9][0-9][0-9].wz"))):
        if path not in _archives:
            _archives[path] = WzArchive(path)
        a = _archives[path]
        entry = a.root.get(name) or next((e for _, e in a.walk() if e.name == name), None)
        if entry is not None:
            _imgs[img_path] = entry.parse()
            return _imgs[img_path]
    raise KeyError(img_path)


def node(img_path, *steps):
    n = read_img(img_path)
    for s in steps:
        n = n[str(s)]
    return n


def picture(n):
    """A canvas node -> an RGBA picture. Follows links (_outlink) into the _Canvas archives."""
    if "link" in n:
        path = n["link"]
        i = path.index(".img/") + 4
        n = node(path[:i], *path[i + 1:].split("/"))
    rgba = decode_canvas(n)
    return None if rgba is None else Image.fromarray(rgba, "RGBA")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    s = WzArchive(os.path.join(DATA, "String", "String_000.wz"))
    eqp = s.find("Eqp.img").parse()["ClassicWorld"]
    names = {}
    for entries in eqp.values():
        for iid, v in entries.items():
            if isinstance(v, dict) and isinstance(v.get("name"), str):
                names[str(int(iid))] = v["name"]

    ids, categories, name_list, sizes, images = [], [], [], [], []
    for category in CATEGORIES:
        a = WzArchive(os.path.join(DATA, "Character", category, category + "_000.wz"))
        n = 0
        for _, e in a.walk():
            if e.kind != "img":
                continue
            info = e.parse().get("info", {})
            if info.get("cash") != 1:
                continue
            iid = str(int(e.name[:-4]))
            # The icon is fetched through the info/iconRaw node's link. It
            # usually points to the item's own file in _Canvas, but colour
            # variants share another item's icon (Black Dress Shoes 1077000 ->
            # 01072999.img). With only the item's own path they were missing:
            # 2,532 icons instead of 2,765, and Black Dress Shoes was read as
            # Brown Dress Shoes (found 2026-11-18).
            try:
                im = picture(info["iconRaw"]) if isinstance(info.get("iconRaw"), dict) \
                    else picture(node("Character/%s/_Canvas/%s" % (category, e.name), "info", "iconRaw"))
            except (KeyError, ValueError):
                continue
            if im is None or im.width > SQUARE or im.height > SQUARE:
                continue
            square = np.zeros((SQUARE, SQUARE, 4), np.uint8)
            square[:im.height, :im.width] = np.asarray(im)
            ids.append(iid); categories.append(category); name_list.append(names.get(iid, ""))
            sizes.append((im.width, im.height)); images.append(square)
            n += 1
        print("%-10s %4d" % (category, n))
    np.savez_compressed(OUT, ids=np.array(ids), categories=np.array(categories),
                        names=np.array(name_list), sizes=np.array(sizes),
                        images=np.stack(images))
    print(OUT, len(ids), "icons", os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
