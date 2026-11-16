"""Känner igen föremålen i inventariets rutor på bilden, mot spelets egna ikoner.

  python icon_match.py <mapp med vy_*.png>      skriv ut vad som ligger i rutorna

Varje ruta skalas ned till spelets egen upplösning (klienten ritar ikonerna
2,75 gånger förstorade i 3840x2160, uppmätt 2026-10-26) och jämförs med alla
ikoner i icon_library.npz, bara på ikonens egna pixlar (alfakanalen som
mask). Ingen hovring och ingen OCR behövs, och ett namn som finns på flera
föremål (White Jeans) avgörs av bilden.
"""
import glob
import os
import re
import sys

import cv2
import numpy as np

from scan_inventory import DX, DY, KOLUMNER, RADER, ar_tom

HERE = os.path.dirname(os.path.abspath(__file__))
SKALA = 2.75
FONSTER = 64          # halva fönstret runt rutans mitt, i klientpixlar
SLOT_RGB = np.array([225, 223, 213], np.float32)   # inventarierutans grå
SUDD = 0.7            # gaussisk suddning av mallarna, i spelets pixlar
TAK = 70.0 ** 2       # tak för felet per pixel: brickan och antalet ska inte dominera


class Bibliotek:
    def __init__(self, fil=os.path.join(HERE, "icon_library.npz")):
        d = np.load(fil)
        self.ids, self.kats, self.namn = d["ids"], d["kats"], d["namn"]
        self.mallar = []
        for b, (w, h) in zip(d["bilder"], d["storlek"]):
            # Klienten skalar upp ikonerna med utjämning, så konturerna i
            # inventariet är mjuka. Mallen suddas lika mycket; med skarpa
            # konturer gav kanterna större fel än skillnaden mellan föremål.
            a = b[:h, :w].astype(np.float32)
            rgb = a[..., :3] * (a[..., 3:] / 255) + SLOT_RGB * (1 - a[..., 3:] / 255)
            rgb = cv2.GaussianBlur(rgb, (0, 0), SUDD)
            mask = cv2.GaussianBlur((a[..., 3] > 128).astype(np.float32), (0, 0), SUDD)
            mask = (mask > 0.15).astype(np.float32)
            self.mallar.append((rgb, cv2.merge([mask, mask, mask])))

    def kanna_igen(self, fonster, kandidater=None, topp=30):
        """fonster: RGB-bild runt en ruta, redan nedskalad till spelets
        upplösning. Ger [(medelfel, index)] sorterat, bäst först.

        Två steg. Först jämförs bara mallens egna pixlar, vilket hittar läget
        och de 30 troligaste. Det steget ensamt föredrar glesa mallar (några
        gnistor passar nästan var som helst mot en ljus ruta), och gav 16 fel
        av 114 på vita föremål. Därför avgör steg två: kandidaten läggs på en
        ruta i inventariets grå på sitt bästa läge, och HELA rutans mitt
        jämförs. Pixlar som mallen inte förklarar räknas då också."""
        f = fonster.astype(np.float32)
        steg1 = []
        for i in (kandidater if kandidater is not None else range(len(self.mallar))):
            rgb, mask = self.mallar[i]
            if rgb.shape[0] > f.shape[0] or rgb.shape[1] > f.shape[1]:
                continue
            res = cv2.matchTemplate(f, rgb, cv2.TM_SQDIFF, mask=mask)
            res[~np.isfinite(res)] = np.inf
            _, _, lage, _ = cv2.minMaxLoc(res)
            steg1.append((float(res.min()) / max(1.0, mask.sum()), i, lage))
        steg1.sort()
        h, w = f.shape[:2]
        y0, y1, x0, x1 = int(h * 0.15), int(h * 0.85), int(w * 0.15), int(w * 0.85)
        bit = f[y0:y1, x0:x1]
        # Cash-brickan (röd-orange "C" nere till höger) är densamma i varje
        # ruta och säger inget om föremålet; dess pixlar räknas inte.
        bricka = (bit[..., 0] > 170) & (bit[..., 1] < 110) & (bit[..., 2] < 90)
        vikt = (~bricka).astype(np.float32)
        ut = []
        for _, i, (lx, ly) in steg1[:topp]:
            rgb, mask = self.mallar[i]
            lagd = np.empty_like(f)
            lagd[:] = SLOT_RGB
            mh, mw = rgb.shape[:2]
            yta = lagd[ly:ly + mh, lx:lx + mw]
            yta[:] = yta * (1 - mask) + rgb * mask
            fel = np.minimum(((lagd[y0:y1, x0:x1] - bit) ** 2).sum(-1) / 3, TAK)
            ut.append((float((fel * vikt).sum() / max(1.0, vikt.sum())), i))
        ut.sort()
        return ut


def kanna_igen_grupp(bib, fonsterlista, topp=30):
    """Samma föremål i flera rutor: felen läggs ihop över rutorna och det
    föremål som passar bäst sammantaget vinner. En enstaka ruta kan annars
    gå fel (en av två Bunny Earmuffs blev Transparent Hat, 2026-10-26).
    Ger (index, medelfel, kvot mot näst bäst)."""
    rankningar = [dict((i, e) for e, i in bib.kanna_igen(f, topp=topp)) for f in fonsterlista]
    alla = set().union(*rankningar)
    summa = {}
    for i in alla:
        # Saknas kandidaten i en rutas topplista räknas rutans sämsta fel.
        summa[i] = sum(r.get(i, max(r.values())) for r in rankningar) / len(rankningar)
    ordning = sorted(alla, key=summa.get)
    bast = ordning[0]
    kvot = summa[ordning[1]] / max(1.0, summa[bast]) if len(ordning) > 1 else 9.9
    return bast, summa[bast], kvot


def fonster(vy_rgb, r, c):
    """Fönstret runt rutan (r, c) i en vy, nedskalat till spelets upplösning."""
    cx, cy = 52 + DX * c, 44 + DY * r
    h, w = vy_rgb.shape[:2]
    bit = vy_rgb[max(0, cy - FONSTER):min(h, cy + FONSTER), max(0, cx - FONSTER):min(w, cx + FONSTER)]
    return cv2.resize(bit, None, fx=1 / SKALA, fy=1 / SKALA, interpolation=cv2.INTER_AREA)


def rutor(mapp):
    """[(inventarierad, kolumn, fönster)] för alla fyllda rutor, en gång var."""
    from PIL import Image
    vyer = {int(re.findall(r"\d+", os.path.basename(f))[0]): f
            for f in glob.glob(os.path.join(mapp, "vy_[0-9]*.png"))}
    ut = []
    for g in range(max(vyer) + RADER):
        k = max(t for t in vyer if t <= g)
        bild = Image.open(vyer[k])
        rgb = np.asarray(bild.convert("RGB"))
        for c in range(KOLUMNER):
            if not ar_tom(bild, g - k, c):
                ut.append((g, c, fonster(rgb, g - k, c)))
    return ut


def main(mapp):
    sys.stdout.reconfigure(encoding="utf-8")
    bib = Bibliotek()
    for g, c, f in rutor(mapp):
        topp = bib.kanna_igen(f)[:2]
        (fel, i), (fel2, _) = topp
        print("rad %2d kol %d  %-28s %s  fel %6.1f  näst bäst %6.1f"
              % (g, c, bib.namn[i], bib.ids[i], fel, fel2))


if __name__ == "__main__":
    main(sys.argv[1])
