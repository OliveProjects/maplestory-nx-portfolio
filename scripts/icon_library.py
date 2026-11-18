"""Bygger ett bibliotek med ikonen för varje cash-föremål ur klientens WZ-filer.

  python icon_library.py

Skriver icon_library.npz bredvid skriptet: id, kategori, namn och ikonen
(iconRaw, RGBA, inklistrad uppe till vänster i en 40x40-ruta). icon_match.py
känner igen inventariets rutor mot det. Bygg om efter en speluppdatering.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

import settings as inst
from wz.img_parser import decode_canvas
from wz.wz_archive import WzArchive

DATA = inst.WZ_DATA
HERE = os.path.dirname(os.path.abspath(__file__))
UT = os.path.join(HERE, "icon_library.npz")
# Kategorier som kan ligga i Deco-fliken. Ansikte, frisyr, afterimage och
# riddjur är aldrig föremål där.
KATEGORIER = ["Accessory", "Cap", "Cape", "Coat", "Glove", "Longcoat", "Pants",
              "PetEquip", "Ring", "Shield", "Shoes", "Weapon"]
RUTA = 40

_arkiv = {}
_img = {}


def las_img(imgvag):
    """'Character/Cap/_Canvas/01002000.img' -> parsat träd, ur rätt arkiv."""
    if imgvag in _img:
        return _img[imgvag]
    mapp, namn = imgvag.rsplit("/", 1)
    bas = os.path.join(DATA, *mapp.split("/"))
    for fil in sorted(glob.glob(os.path.join(bas, os.path.basename(bas) + "_[0-9][0-9][0-9].wz"))):
        if fil not in _arkiv:
            _arkiv[fil] = WzArchive(fil)
        a = _arkiv[fil]
        post = a.root.get(namn) or next((e for _, e in a.walk() if e.name == namn), None)
        if post is not None:
            _img[imgvag] = post.parse()
            return _img[imgvag]
    raise KeyError(imgvag)


def nod(imgvag, *steg):
    n = las_img(imgvag)
    for s in steg:
        n = n[str(s)]
    return n


def bild(n):
    """Canvas-nod -> RGBA-bild. Följer länkar (_outlink) till _Canvas-arkiven."""
    if "link" in n:
        vag = n["link"]
        i = vag.index(".img/") + 4
        n = nod(vag[:i], *vag[i + 1:].split("/"))
    rgba = decode_canvas(n)
    return None if rgba is None else Image.fromarray(rgba, "RGBA")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    s = WzArchive(os.path.join(DATA, "String", "String_000.wz"))
    eqp = s.find("Eqp.img").parse()["ClassicWorld"]
    namn = {}
    for poster in eqp.values():
        for iid, v in poster.items():
            if isinstance(v, dict) and isinstance(v.get("name"), str):
                namn[str(int(iid))] = v["name"]

    ids, kats, namnlista, storlek, bilder = [], [], [], [], []
    for kat in KATEGORIER:
        a = WzArchive(os.path.join(DATA, "Character", kat, kat + "_000.wz"))
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
            # 2,532 icons instead of 2,750, and Black Dress Shoes was read as
            # Brown Dress Shoes (found 2026-11-18).
            try:
                im = bild(info["iconRaw"]) if isinstance(info.get("iconRaw"), dict) \
                    else bild(nod("Character/%s/_Canvas/%s" % (kat, e.name), "info", "iconRaw"))
            except (KeyError, ValueError):
                continue
            if im is None or im.width > RUTA or im.height > RUTA:
                continue
            ruta = np.zeros((RUTA, RUTA, 4), np.uint8)
            ruta[:im.height, :im.width] = np.asarray(im)
            ids.append(iid); kats.append(kat); namnlista.append(namn.get(iid, ""))
            storlek.append((im.width, im.height)); bilder.append(ruta)
            n += 1
        print("%-10s %4d" % (kat, n))
    np.savez_compressed(UT, ids=np.array(ids), kats=np.array(kats),
                        namn=np.array(namnlista), storlek=np.array(storlek),
                        bilder=np.stack(bilder))
    print(UT, len(ids), "ikoner", os.path.getsize(UT) // 1024, "KB")


if __name__ == "__main__":
    main()
