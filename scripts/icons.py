"""Fetches the icon of every item in deco.json from the client's WZ files.

  python icons.py              (the icons go to the page's icons/)
  python icons.py <out folder>

The name is looked up in String/Eqp.img (under ClassicWorld); the icon is in
Character/<category>/_Canvas/_Canvas_000.wz as <id>.img/info/iconRaw.
Saves <out folder>/<id>.png and writes the id and category back to
deco.json. If a name has several ids, the one deco.json already gives (the
"id" field) is chosen; without it every candidate is saved and the script
says so.
"""
import os
import sys

from PIL import Image

import settings as cfg
from common import read_deco, write_json, DECO
from wz.img_parser import decode_canvas
from wz.wz_archive import WzArchive

DATA = cfg.WZ_DATA
HERE = os.path.dirname(os.path.abspath(__file__))


def catalog():
    """({name: [(category, id)]}, {id: (name, category)}) for every equipment
    item in Classic."""
    s = WzArchive(os.path.join(DATA, "String", "String_000.wz"))
    eqp = s.find("Eqp.img").parse()["ClassicWorld"]
    by_name, by_id = {}, {}
    for category, entries in eqp.items():
        for iid, v in entries.items():
            if isinstance(v, dict) and isinstance(v.get("name"), str):
                iid = str(int(iid))
                by_name.setdefault(v["name"], []).append((category, iid))
                by_id[iid] = (v["name"], category)
    return by_name, by_id


def icon(category, iid, archives={}):
    """The icon lies in _Canvas under the file the item's info/iconRaw links
    to. Usually the item's own, but colour variants share another item's
    icon (Black Dress Shoes 1077000 -> 01072999.img)."""
    for name in (category + "_000.wz", os.path.join("_Canvas", "_Canvas_000.wz")):
        if (category, name) not in archives:
            archives[category, name] = WzArchive(os.path.join(DATA, "Character", category, name))
    path = "%08d.img" % int(iid)
    entry = archives[category, category + "_000.wz"].find(path)
    if entry is not None:
        link = (entry.parse().get("info", {}).get("iconRaw") or {}).get("link", "")
        if link.startswith("Character/%s/_Canvas/" % category) and ".img/" in link:
            path = link.split("/")[3]
    entry = archives[category, os.path.join("_Canvas", "_Canvas_000.wz")].find(path)
    if entry is None:
        return None
    info = entry.parse().get("info", {})
    rgba = decode_canvas(info.get("iconRaw") or info.get("icon"))
    return None if rgba is None else Image.fromarray(rgba, "RGBA")


def main(out):
    # Run from sync.py, stdout is the log writer (Tee), already UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(out, exist_ok=True)
    deco = read_deco()
    by_name = catalog()[0]
    for f in deco["items"]:
        candidates = by_name.get(f["name"], [])
        if f.get("id"):
            candidates = [k for k in candidates if k[1] == f["id"]]
        if not candidates:
            print("MISSING:", f["name"])
            continue
        for category, iid in candidates:
            img = icon(category, iid)
            if img is None:
                print("no icon:", f["name"], category, iid)
                continue
            img.save(os.path.join(out, "%s.png" % iid))
        if len(candidates) == 1:
            f["category"], f["id"] = candidates[0]
        else:
            print("SEVERAL:", f["name"], candidates)
    write_json(DECO, deco)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(cfg.page_dir(), "icons"))
