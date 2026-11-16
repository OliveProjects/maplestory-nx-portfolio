"""What Synka.bat shows: a menu of what you can do.

  1  Scan the Deco tab in the game        (synka.py)
  2  Sync from your list                  (synka.py --lista mina_foremal.txt)
  3  Set the mesos : NX rate              (data/nx_rates.json on your site)
  4  Update your site to this version     (website_creator.py --update)
  5  Enter prices yourself                (paste a price list; today's prices)

The rate is how many mesos 1k NX costs in the game right now, plus what
1k NX costs in dollars from Nexon. The page's NX and $ tiles and the $
chart use it. Each change is saved with today's date, so the $ chart
values every day at the rate that applied then.

    python meny.py
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
    import installningar as inst
    return os.path.join(inst.data(), "nx_rates.json"), inst


def las_kurser(fil):
    if os.path.exists(fil):
        return json.load(open(fil, encoding="utf-8"))
    return {"usd_per_1k_nx": STANDARD["usd_per_1k_nx"], "rates": []}


def satt_kurs():
    import gemensamt
    fil, inst = kurser_fil()
    data = las_kurser(fil)
    nu = data["rates"][-1]["mesos_per_1k_nx"] if data["rates"] else None
    print()
    if nu:
        print("  The rate now: 1k NX = %s mesos (since %s), 1k NX = $%s from Nexon."
              % (format(nu, ","), data["rates"][-1]["from"], data.get("usd_per_1k_nx", 1)))
    svar = input("  How many mesos does 1k NX cost in the game now? (e.g. 20k, Enter = keep): ").strip()
    ny = gemensamt.tolka(svar) if svar else None
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


def tolka_prislista(rader, tolka):
    """{name in lower case: price} from a pasted list. Understands blocks of
    name, a line starting with "Cash Shop", then a line that starts with the
    price (like a price site's table copied from the browser), and plain
    lines like "Angel Halo<tab>950k" or "Angel Halo: 950k"."""
    rena = [r.strip() for r in rader if r.strip()]
    priser = {}
    for i, r in enumerate(rena[:-2]):
        if rena[i + 1].lower().startswith("cash shop"):
            delar = rena[i + 2].split()
            pris = tolka(delar[0]) if delar else None
            if pris:
                priser[r.lower()] = pris
    if not priser:
        for r in rena:
            m = re.match(r"(.+?)\s*[\t;:=|]\s*([\d.,]+\s*[kmb]?)\s*$", r, re.I)
            if m and tolka(m.group(2).replace(" ", "")):
                priser[m.group(1).strip().lower()] = tolka(m.group(2).replace(" ", ""))
    return priser


def ange_priser():
    """Today's prices by hand: paste a list, match it to the inventory,
    show the result, ask where the prices are from, then publish. They
    become today's point in prices.json and the page's current prices."""
    import gemensamt
    import installningar as inst
    data = inst.data()
    inv = json.load(open(os.path.join(data, "inventory.json"), encoding="utf-8"))["items"]
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
    lista = tolka_prislista(rader, gemensamt.tolka)
    if not lista:
        print("  Found no prices in that. Nothing changed.")
        return
    traff = {it["id"]: lista[it["name"].lower()] for it in inv if it["name"].lower() in lista}
    saknas = [it["name"] for it in inv if it["id"] not in traff]
    varde = sum(traff[it["id"]] * it["qty"] for it in inv if it["id"] in traff)
    print("\n  Read %d prices. %d of your %d kinds matched; together they are worth %s mesos."
          % (len(lista), len(traff), len(inv), format(varde, ",")))
    if saknas:
        print("  No price for: " + ", ".join(saknas[:12]) + (" …" if len(saknas) > 12 else ""))
        print("  (Those keep their last price.)")
    if not traff:
        return
    kalla = input("  Where are these prices from? It is shown on your page as the source: ").strip()
    if not kalla:
        print("  A source is needed, so visitors know where the prices come from. Nothing changed.")
        return
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
        sista["manual"] = kalla
    else:
        pj["updates"].append({"date": idag, "prices": {**{i: p for i, p in sista["prices"].items() if i in antal}, **traff},
                              "qty": antal, "manual": kalla})
    gemensamt.skriv_json(pfil, pj)
    lfil = os.path.join(data, "live.json")
    live = json.load(open(lfil, encoding="utf-8")) if os.path.exists(lfil) else {"items": {}}
    for i, p in traff.items():
        live["items"][i] = {"p": p, "w": "manual"}
    live.update({"updated": int(time.time()), "manual": kalla, "manual_date": idag})
    gemensamt.skriv_json(lfil, live)

    git = ["git", "-C", inst.WEB]
    subprocess.run(git + ["pull", "-q", "--rebase", "--autostash", inst.REMOTES[0], "main"])
    subprocess.run(git + ["add", os.path.relpath(pfil, inst.WEB), os.path.relpath(lfil, inst.WEB)], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "MapleStory: prices for %d kinds entered by hand (%s)" % (len(traff), kalla)], check=True)
    for r in inst.REMOTES:
        subprocess.run(git + ["push", "-q", r, "main"], check=True)
    print("  Published: %d prices from %s, today's value %s mesos." % (len(traff), kalla, format(varde, ",")))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(HERE, "installningar.json")):
        print("No site yet. Run python website_creator.py first.")
        return
    while True:
        print("""
What do you want to do?
  1  Scan the Deco tab in the game
  2  Sync from your list (mina_foremal.txt)
  3  Set the mesos : NX rate
  4  Update your site to this version
  5  Enter prices yourself (paste a price list)
  q  Quit""")
        val = input("> ").strip().lower()
        if val == "1":
            print("\n  Open Item Inventory in the game and select the Deco tab first.")
            subprocess.run([sys.executable, os.path.join(HERE, "synka.py")])
        elif val == "2":
            subprocess.run([sys.executable, os.path.join(HERE, "synka.py"), "--lista", os.path.join(HERE, "mina_foremal.txt")])
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
