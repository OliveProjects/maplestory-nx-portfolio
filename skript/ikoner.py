"""Hämtar ikonen för varje föremål i deco.json ur klientens WZ-filer.

  python ikoner.py            (ikonerna hamnar i sidans icons/)
  python ikoner.py <utmapp>

Namnet slås upp i String/Eqp.img (under ClassicWorld), ikonen ligger i
Character/<kategori>/_Canvas/_Canvas_000.wz som <id>.img/info/iconRaw.
Sparar <utmapp>/<id>.png och skriver id och kategori tillbaka i deco.json.
Har ett namn flera id väljs det som deco.json redan anger (fältet "id");
saknas det sparas alla kandidater och skriptet säger till.
"""
import json
import os
import sys

from PIL import Image

import installningar as inst
from wz.img_parser import decode_canvas
from wz.wz_archive import WzArchive

DATA = inst.WZ_DATA
HERE = os.path.dirname(os.path.abspath(__file__))
DECO = os.path.join(HERE, "deco.json")


def katalog():
    """({namn: [(kategori, id)]}, {id: (namn, kategori)}) för alla
    utrustningsföremål i Classic."""
    s = WzArchive(os.path.join(DATA, "String", "String_000.wz"))
    eqp = s.find("Eqp.img").parse()["ClassicWorld"]
    namn, per_id = {}, {}
    for kat, poster in eqp.items():
        for iid, v in poster.items():
            if isinstance(v, dict) and isinstance(v.get("name"), str):
                iid = str(int(iid))
                namn.setdefault(v["name"], []).append((kat, iid))
                per_id[iid] = (v["name"], kat)
    return namn, per_id


def namn_till_id():
    return katalog()[0]


def ikon(kat, iid, arkiv={}):
    if kat not in arkiv:
        arkiv[kat] = WzArchive(os.path.join(DATA, "Character", kat,
                                            "_Canvas", "_Canvas_000.wz"))
    post = arkiv[kat].find("%08d.img" % int(iid))
    if post is None:
        return None
    info = post.parse().get("info", {})
    rgba = decode_canvas(info.get("iconRaw") or info.get("icon"))
    return None if rgba is None else Image.fromarray(rgba, "RGBA")


def main(ut):
    # Inifrån synka.py är stdout loggskrivaren (Dubbel), som redan är UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(ut, exist_ok=True)
    deco = json.load(open(DECO, encoding="utf-8"))
    karta = namn_till_id()
    for f in deco["foremal"]:
        kandidater = karta.get(f["namn"], [])
        if f.get("id"):
            kandidater = [k for k in kandidater if k[1] == f["id"]]
        if not kandidater:
            print("SAKNAS:", f["namn"])
            continue
        for kat, iid in kandidater:
            bild = ikon(kat, iid)
            if bild is None:
                print("ingen ikon:", f["namn"], kat, iid)
                continue
            bild.save(os.path.join(ut, "%s.png" % iid))
        if len(kandidater) == 1:
            f["kategori"], f["id"] = kandidater[0]
        else:
            print("FLERA:", f["namn"], kandidater)
    with open(DECO, "w", encoding="utf-8") as fh:
        json.dump(deco, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(inst.sida(), "icons"))
