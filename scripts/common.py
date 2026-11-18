"""What sync.py and market_prices.py share: the files in the site repo, the
page's inventory.json, and reading amounts like 480k or 1.2m.

Writes in the site repo (the subfolder from settings.json):
  data/inventory.json  items and counts, from deco.json
  data/prices.json     one entry per date with prices and counts. Entries
                       with "inventory": true come from sync.py and carry the
                       day before's prices with the new counts.
icons.py puts the icons in icons/.
"""
import json
import os
import re

from PIL import Image

import settings as cfg

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = cfg.WEB
PAGE = cfg.page_dir()
INVENTORY = os.path.join(PAGE, "data", "inventory.json")
PRICES = os.path.join(PAGE, "data", "prices.json")
DECO = os.path.join(HERE, "deco.json")

# The client's categories with the names the game shows in its tooltip ("Type").
SLOT_NAMES = {"Cap": "Hat", "Coat": "Top", "Longcoat": "Overall", "Pants": "Bottom",
              "Shoes": "Shoes", "Glove": "Gloves", "Cape": "Cape", "Ring": "Ring",
              "Weapon": "Weapon", "Accessory": "Accessory"}

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def read_deco():
    """deco.json, the last sync's inventory, as {"date", "items": [{"name",
    "count", "category", "id"}]}. Files from older versions, with Swedish
    keys (datum, foremal, namn, antal, kategori), are read too."""
    if not os.path.exists(DECO):
        return None
    d = json.load(open(DECO, encoding="utf-8"))
    if "items" in d:
        return d
    return {"date": d.get("datum"),
            "items": [{"name": f["namn"], "count": f["antal"], "category": f.get("kategori"), "id": f.get("id")}
                      for f in d.get("foremal", [])]}


def write_deco(date, items):
    """items: {id: (name, category, count)}."""
    write_json(DECO, {"date": date, "items": [{"name": n, "count": c, "category": k, "id": i}
                                              for i, (n, k, c) in items.items()]})


def write_inventory():
    deco = read_deco()
    items = []
    for f in deco["items"]:
        icon = os.path.join(PAGE, "icons", f["id"] + ".png")
        if not os.path.exists(icon):
            raise SystemExit("no icon for %s; run icons.py first" % f["name"])
        w, h = Image.open(icon).size
        items.append({"id": f["id"], "name": f["name"], "qty": f["count"],
                      "slot": SLOT_NAMES.get(f["category"], f["category"]),
                      "w": w, "h": h})
    write_json(INVENTORY, {"date": deco["date"], "items": items})
    return items


def parse_amount(text):
    """480000, 480,000, 480k, 1.2m or 2b -> a whole number; anything else -> None."""
    s = text.strip().lower().replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", s)
    if not m:
        return None
    factor = {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)]
    return int(round(float(m.group(1)) * factor))
