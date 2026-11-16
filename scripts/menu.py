"""What Sync.bat shows: a menu of what you can do.

  1  Scan the Deco tab in the game        (sync.py)
  2  Sync from your list                  (sync.py --lista my_items.txt)
  3  Set the mesos : NX rate              (data/nx_rates.json on your site)
  4  Update your site to this version     (website_creator.py --update)
  5  Enter prices yourself                (paste a price list; today's prices)

The rate is how many mesos 1k NX costs in the game right now, plus what
1k NX costs in dollars from Nexon. The page's NX and $ tiles and the $
chart use it. Each change is saved with today's date, so the $ chart
values every day at the rate that applied then.

    python menu.py
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STANDARD = {"mesos_per_1k_nx": 20000, "usd_per_1k_nx": 1}


def kurser_fil():
    import settings as inst
    return os.path.join(inst.data(), "nx_rates.json"), inst


def las_kurser(fil):
    if os.path.exists(fil):
        return json.load(open(fil, encoding="utf-8"))
    return {"usd_per_1k_nx": STANDARD["usd_per_1k_nx"], "rates": []}


def satt_kurs():
    import common
    fil, inst = kurser_fil()
    data = las_kurser(fil)
    nu = data["rates"][-1]["mesos_per_1k_nx"] if data["rates"] else None
    print()
    if nu:
        print("  The rate now: 1k NX = %s mesos (since %s), 1k NX = $%s from Nexon."
              % (format(nu, ","), data["rates"][-1]["from"], data.get("usd_per_1k_nx", 1)))
    svar = input("  How many mesos does 1k NX cost in the game now? (e.g. 20k, Enter = keep): ").strip()
    ny = common.tolka(svar) if svar else None
    if svar and not ny:
        print("  Could not read that. Write a number, e.g. 20000 or 20k.")
        return
    usd_svar = input("  What does 1k NX cost in dollars from Nexon? (Enter = $%s): " % data.get("usd_per_1k_nx", 1)).strip()
    if usd_svar:
        try:
            data["usd_per_1k_nx"] = float(usd_svar.replace("$", "").replace(",", "."))
        except ValueError:
            print("  Could not read that dollar amount; it stays $%s." % data.get("usd_per_1k_nx", 1))
    idag = datetime.date.today().isoformat()
    if ny:
        if data["rates"] and data["rates"][-1]["from"] == idag:
            data["rates"][-1]["mesos_per_1k_nx"] = ny
        elif ny != nu:
            data["rates"].append({"from": idag, "mesos_per_1k_nx": ny})
    if not data["rates"]:
        data["rates"].append({"from": idag, "mesos_per_1k_nx": STANDARD["mesos_per_1k_nx"]})
    os.makedirs(os.path.dirname(fil), exist_ok=True)
    with open(fil, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    git = ["git", "-C", inst.WEB]
    subprocess.run(git + ["pull", "-q", "--rebase", "--autostash", inst.REMOTES[0], "main"])
    subprocess.run(git + ["add", os.path.relpath(fil, inst.WEB)], check=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        print("  Nothing changed.")
        return
    subprocess.run(git + ["commit", "-q", "-m", "MapleStory: NX rate %s mesos per 1k NX"
                          % format(data["rates"][-1]["mesos_per_1k_nx"], ",")], check=True)
    for r in inst.REMOTES:
        subprocess.run(git + ["push", "-q", r, "main"], check=True)
    print("  Saved and published: 1k NX = %s mesos, $%s from Nexon."
          % (format(data["rates"][-1]["mesos_per_1k_nx"], ","), data["usd_per_1k_nx"]))


# A mesos amount: 950K, 1.1M, 8,999, 2b. Not a percentage, an NX price, a
# multiplier or a count of sales (those follow the number).
BELOPP = re.compile(r"(?<![\w.,+−-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?([kmb])?(?!\s*(?:%|nx\b|×|x\b|sales?\b))(?![\w.,%])", re.I)
FYLLNAD = ("cash shop", "volatile", "low data", "too few days", "not on sale now")


def belopp_i(rad):
    """The first mesos amount on a line (at least 100 mesos), or None."""
    for m in BELOPP.finditer(rad):
        v = float(m.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1)
        if v >= 100:
            return int(round(v))
    return None


def tolka_prislista(rader, mina, alla_namn=()):
    """{item id: price} for your items, from a pasted list in any layout.

    It starts from the names: every line that is one of your items is an
    anchor, wherever it stands. The price is the first mesos amount after
    it, on the same line or the lines below; percentages, NX prices,
    multipliers, sales counts and filler lines ("Cash Shop", "volatile")
    are skipped. The search stops at the next item name (any item in the
    game, when the game's names are known) or at "No sales", so an item
    without a price never gets the next item's. A name and a price on one
    line work in either order ("Angel Halo 950k", "950k Angel Halo").
    mina = {name in lower case: [ids]}."""
    rena = [r.strip() for r in rader if r.strip()]
    stopp = set(alla_namn) | set(mina)
    def namn_pa(rad):
        """The item name a line holds, with any amount and separators taken off."""
        utan = re.sub(r"[\t;:=|]+", " ", BELOPP.sub(" ", rad)).strip(" -–").lower()
        return " ".join(utan.split())
    priser = {}
    for i, rad in enumerate(rena):
        namn = rad.lower() if rad.lower() in mina else namn_pa(rad)
        if namn not in mina or any(i2 in priser for i2 in mina[namn]):
            continue
        pris = belopp_i(rad) if namn != rad.lower() else None
        for nasta in rena[i + 1:i + 10]:
            if pris:
                break
            lag = nasta.lower()
            if "no sales" in lag or lag in stopp or namn_pa(nasta) in stopp:
                break
            if lag.startswith(FYLLNAD):
                continue
            pris = belopp_i(nasta)
        if pris:
            for iid in mina[namn]:
                priser[iid] = pris
    return priser


def ange_priser():
    """Today's prices by hand: paste a list, match it to the inventory,
    show the result, then publish on yes. They become today's point in
    prices.json and the page's current prices."""
    import common
    import settings as inst
    data = inst.data()
    inv = json.load(open(os.path.join(data, "inventory.json"), encoding="utf-8"))["items"]
    mina = {}
    for it in inv:
        mina.setdefault(it["name"].lower(), []).append(it["id"])
    try:   # every item name in the game, so the search stops at any item
        from icons import katalog
        alla_namn = {n.lower() for n in katalog()[0]}
    except Exception:  # noqa: BLE001  (no game files: your own names only)
        alla_namn = set()
    print("""
  Paste the prices (for example a price site's table copied from the browser,
  or one item per line like "Angel Halo<tab>950k"). Then type END on its own
  line and press Enter.
  Note: if your hourly maplestory.market job runs, it replaces these prices
  within the hour. This is for when you have no key or the market has no data.""")
    rader = []
    while True:
        try:
            rad = input()
        except EOFError:
            break
        if rad.strip().upper() == "END":
            break
        rader.append(rad)
    traff = tolka_prislista(rader, mina, alla_namn)
    if not traff:
        print("  Found none of your items with a price in that. Nothing changed.")
        return
    saknas = [it["name"] for it in inv if it["id"] not in traff]
    varde = sum(traff[it["id"]] * it["qty"] for it in inv if it["id"] in traff)
    print("\n  %d of your %d kinds got a price; together they are worth %s mesos:" % (len(traff), len(inv), format(varde, ",")))
    for it in sorted((it for it in inv if it["id"] in traff), key=lambda it: -traff[it["id"]] * it["qty"]):
        print("    %-30s %12s  × %d" % (it["name"][:30], format(traff[it["id"]], ","), it["qty"]))
    if saknas:
        print("  No price for: " + ", ".join(saknas[:12]) + (" …" if len(saknas) > 12 else ""))
        print("  (Those keep their last price.)")
    if input("  Publish these as today's prices? [y/N] ").strip().lower() not in ("y", "yes", "j", "ja"):
        print("  Nothing changed.")
        return

    idag = datetime.date.today().isoformat()
    pfil = os.path.join(data, "prices.json")
    pj = json.load(open(pfil, encoding="utf-8"))
    antal = {it["id"]: it["qty"] for it in inv}
    sista = pj["updates"][-1]
    if sista["date"] == idag:
        sista["prices"].update(traff)
        sista["manual"] = True
    else:
        pj["updates"].append({"date": idag, "prices": {**{i: p for i, p in sista["prices"].items() if i in antal}, **traff},
                              "qty": antal, "manual": True})
    common.skriv_json(pfil, pj)
    lfil = os.path.join(data, "live.json")
    live = json.load(open(lfil, encoding="utf-8")) if os.path.exists(lfil) else {"items": {}}
    for i, p in traff.items():
        live["items"][i] = {"p": p, "w": "manual"}
    live.update({"updated": int(time.time()), "manual": True, "manual_date": idag})
    common.skriv_json(lfil, live)

    git = ["git", "-C", inst.WEB]
    subprocess.run(git + ["pull", "-q", "--rebase", "--autostash", inst.REMOTES[0], "main"])
    subprocess.run(git + ["add", os.path.relpath(pfil, inst.WEB), os.path.relpath(lfil, inst.WEB)], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "MapleStory: prices for %d kinds entered by hand" % len(traff)], check=True)
    for r in inst.REMOTES:
        subprocess.run(git + ["push", "-q", r, "main"], check=True)
    print("  Published: %d prices entered by hand, today's value of those %s mesos." % (len(traff), format(varde, ",")))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(HERE, "settings.json")):
        print("No site yet. Run python website_creator.py first.")
        return
    while True:
        print("""
What do you want to do?
  1  Scan the Deco tab in the game
  2  Sync from your list (my_items.txt)
  3  Set the mesos : NX rate
  4  Update your site to this version
  5  Enter prices yourself (paste a price list)
  q  Quit""")
        val = input("> ").strip().lower()
        if val == "1":
            print("\n  Open Item Inventory in the game and select the Deco tab first.")
            subprocess.run([sys.executable, os.path.join(HERE, "sync.py")])
        elif val == "2":
            subprocess.run([sys.executable, os.path.join(HERE, "sync.py"), "--lista", os.path.join(HERE, "my_items.txt")])
        elif val == "3":
            satt_kurs()
        elif val == "4":
            subprocess.run([sys.executable, os.path.join(HERE, "website_creator.py"), "--update"])
        elif val == "5":
            ange_priser()
        elif val in ("q", "quit", ""):
            return
        else:
            print("  Pick 1, 2, 3, 4, 5 or q.")


if __name__ == "__main__":
    main()
