"""Det som sync.py och market_prices.py delar: filerna i webbrepot,
sidans inventory.json och tolkningen av priser som 480k eller 1.2m.

Skriver i webbrepot (undermappen ur settings.json):
  data/inventory.json  föremål och antal, ur deco.json
  data/prices.json     en post per datum med priser och antal. Poster med
                       "inventory": true kommer från sync.py och bär förra
                       dagens priser med nya antal.
Ikonerna läggs i icons/ av icons.py.
"""
import json
import os
import re

from PIL import Image

import settings as inst

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = inst.WEB
SIDA = inst.sida()
INVENTORY = os.path.join(SIDA, "data", "inventory.json")
PRICES = os.path.join(SIDA, "data", "prices.json")
DECO = os.path.join(HERE, "deco.json")

# Klientens kategorier med de namn spelet själv visar i tooltipen ("Type").
PLATS = {"Cap": "Hat", "Coat": "Top", "Longcoat": "Overall", "Pants": "Bottom",
         "Shoes": "Shoes", "Glove": "Gloves", "Cape": "Cape", "Ring": "Ring",
         "Weapon": "Weapon", "Accessory": "Accessory"}

MANADER = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def skriv_json(fil, data):
    os.makedirs(os.path.dirname(fil), exist_ok=True)
    with open(fil, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def skriv_inventory():
    deco = json.load(open(DECO, encoding="utf-8"))
    items = []
    for f in deco["foremal"]:
        ikon = os.path.join(SIDA, "icons", f["id"] + ".png")
        if not os.path.exists(ikon):
            raise SystemExit("ikon saknas för %s, kör icons.py först" % f["namn"])
        w, h = Image.open(ikon).size
        items.append({"id": f["id"], "name": f["namn"], "qty": f["antal"],
                      "slot": PLATS.get(f["kategori"], f["kategori"]),
                      "w": w, "h": h})
    skriv_json(INVENTORY, {"date": deco["datum"], "items": items})
    return items


def tolka(svar):
    """480000, 480,000, 480k, 1.2m eller 2b -> heltal; annat -> None."""
    s = svar.strip().lower().replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", s)
    if not m:
        return None
    faktor = {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)]
    return int(round(float(m.group(1)) * faktor))
