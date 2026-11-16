"""Grupperar inventarierutorna efter ikon och räknar hur många av varje.

  python gruppera.py <mapp med vy_*.png> <ocr.json>

Ikonerna jämförs i stället för OCR-texten, eftersom tooltipen för de högra
kolumnerna öppnas åt vänster och urklippet då fångar jämförelsen med det
föremål som bärs. Namnet tas från den ruta i gruppen som står längst till
vänster.
"""
import glob
import json
import os
import re
import sys

import numpy as np
from PIL import Image

from inventera import CELL, DX, DY, KOLUMNER, RADER, ar_tom

GRANS = 20   # medelavvikelse efter passning; olika föremål ger över 70
GLAPP = 10   # rutnätets steg är inte exakt DX/DY, så sök passning ±GLAPP px
INRE = CELL - GLAPP


def ikon(vy, r, c):
    a = np.asarray(vy.convert("L"), dtype=np.int16)
    cx, cy = 52 + DX * c, 44 + DY * r
    return a[cy - CELL:cy + CELL, cx - CELL:cx + CELL]


def avstand(a, b):
    """Minsta medelavvikelse mellan mitten av a och b förskjuten upp till
    GLAPP px åt varje håll."""
    k = a[GLAPP:GLAPP + 2 * INRE, GLAPP:GLAPP + 2 * INRE]
    return min(np.abs(k - b[dy:dy + 2 * INRE, dx:dx + 2 * INRE]).mean()
               for dy in range(2 * GLAPP + 1) for dx in range(2 * GLAPP + 1))


def grupper(mapp, ocrfil=None):
    """[{"rutor": [(rad, kol)], "texter": [(kol, [rader])]}], en per ikon,
    i inventariets ordning. texter är OCR-läsningarna för gruppens rutor
    (tomma utan ocrfil; synka.py känner igen på bilden i stället)."""
    # vy_NN.png: inventariets rad NN står överst i vyn.
    vyer = {int(re.findall(r"\d+", os.path.basename(f))[0]): f
            for f in glob.glob(os.path.join(mapp, "vy_[0-9]*.png"))}
    ocr = ({(e["rad"], e["kolumn"]): e["text"]
            for e in json.load(open(ocrfil, encoding="utf-8"))} if ocrfil else {})
    grp = []   # [ikon, [(rad, kol)]]
    for g in range(max(vyer) + RADER):
        k = max(t for t in vyer if t <= g)
        vy = Image.open(vyer[k])
        r = g - k
        for c in range(KOLUMNER):
            if ar_tom(vy, r, c):
                continue
            i = ikon(vy, r, c)
            for g_ in grp:
                if avstand(g_[0], i) < GRANS:
                    g_[1].append((g, c))
                    break
            else:
                grp.append([i, [(g, c)]])
    return [{"rutor": rutor,
             "texter": [(c, ocr.get((g, c), [])) for g, c in rutor]}
            for _, rutor in grp]


def main(mapp, ocrfil):
    sys.stdout.reconfigure(encoding="utf-8")
    gs = grupper(mapp, ocrfil)
    for gr in gs:
        c, text = min(gr["texter"], key=lambda t: t[0])
        print("%2d st  rad %2d  %s" % (len(gr["rutor"]), gr["rutor"][0][0], " | ".join(text) or "?"))
    print(sum(len(g["rutor"]) for g in gs), "föremål i", len(gs), "grupper")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
