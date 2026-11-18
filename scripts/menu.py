"""What Sync.bat shows: a menu of what you can do.

  1  Scan the Deco tab in the game        (sync.py; the script scrolls)
  2  Read your own screenshots            (sync.py --screenshots; never touches the game)
  3  Sync from your list                  (sync.py --list my_items.txt)
  4  Set the mesos : NX rate              (data/nx_rates.json on your site)
  5  Update your site to this version     (website_creator.py --update)
  6  Enter prices yourself                (paste a price list; today's prices)

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
DEFAULT = {"mesos_per_1k_nx": 20000, "usd_per_1k_nx": 1}


def rates_file():
    import settings as cfg
    return os.path.join(cfg.data_dir(), "nx_rates.json"), cfg


def read_rates(path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return {"usd_per_1k_nx": DEFAULT["usd_per_1k_nx"], "rates": []}


def set_rate():
    import common
    path, cfg = rates_file()
    data = read_rates(path)
    now = data["rates"][-1]["mesos_per_1k_nx"] if data["rates"] else None
    print()
    if now:
        print("  The rate now: 1k NX = %s mesos (since %s), 1k NX = $%s from Nexon."
              % (format(now, ","), data["rates"][-1]["from"], data.get("usd_per_1k_nx", 1)))
    answer = input("  How many mesos does 1k NX cost in the game now? (e.g. 20k, Enter = keep): ").strip()
    new = common.parse_amount(answer) if answer else None
    if answer and not new:
        print("  Could not read that. Write a number, e.g. 20000 or 20k.")
        return
    usd_answer = input("  What does 1k NX cost in dollars from Nexon? (Enter = $%s): " % data.get("usd_per_1k_nx", 1)).strip()
    if usd_answer:
        try:
            data["usd_per_1k_nx"] = float(usd_answer.replace("$", "").replace(",", "."))
        except ValueError:
            print("  Could not read that dollar amount; it stays $%s." % data.get("usd_per_1k_nx", 1))
    today = datetime.date.today().isoformat()
    if new:
        if data["rates"] and data["rates"][-1]["from"] == today:
            data["rates"][-1]["mesos_per_1k_nx"] = new
        elif new != now:
            data["rates"].append({"from": today, "mesos_per_1k_nx": new})
    if not data["rates"]:
        data["rates"].append({"from": today, "mesos_per_1k_nx": DEFAULT["mesos_per_1k_nx"]})
    common.write_json(path, data)
    git = ["git", "-C", cfg.WEB]
    subprocess.run(git + ["pull", "-q", "--rebase", "--autostash", cfg.REMOTES[0], "main"])
    subprocess.run(git + ["add", os.path.relpath(path, cfg.WEB)], check=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        print("  Nothing changed.")
        return
    subprocess.run(git + ["commit", "-q", "-m", "MapleStory: NX rate %s mesos per 1k NX"
                          % format(data["rates"][-1]["mesos_per_1k_nx"], ",")], check=True)
    for r in cfg.REMOTES:
        subprocess.run(git + ["push", "-q", r, "main"], check=True)
    print("  Saved and published: 1k NX = %s mesos, $%s from Nexon."
          % (format(data["rates"][-1]["mesos_per_1k_nx"], ","), data["usd_per_1k_nx"]))


# A mesos amount: 950K, 1.1M, 8,999, 2b. Not a percentage, an NX price, a
# multiplier or a count of sales (those follow the number).
AMOUNT = re.compile(r"(?<![\w.,+−-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?([kmb])?(?!\s*(?:%|nx\b|×|x\b|sales?\b))(?![\w.,%])", re.I)
FILLER = ("cash shop", "volatile", "low data", "too few days", "not on sale now")


def amount_in(line):
    """The first mesos amount on a line (at least 100 mesos), or None."""
    for m in AMOUNT.finditer(line):
        v = float(m.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1)
        if v >= 100:
            return int(round(v))
    return None


def parse_price_list(lines, mine, all_names=()):
    """{item id: price} for your items, from a pasted list in any layout.

    It starts from the names: every line that is one of your items is an
    anchor, wherever it stands. The price is the first mesos amount after
    it, on the same line or the lines below; percentages, NX prices,
    multipliers, sales counts and filler lines ("Cash Shop", "volatile")
    are skipped. The search stops at the next item name (any item in the
    game, when the game's names are known) or at "No sales", so an item
    without a price never gets the next item's. A name and a price on one
    line work in either order ("Angel Halo 950k", "950k Angel Halo").
    mine = {name in lower case: [ids]}."""
    clean = [r.strip() for r in lines if r.strip()]
    stops = set(all_names) | set(mine)

    def name_on(line):
        """The item name a line holds, with any amount and separators taken off."""
        bare = re.sub(r"[\t;:=|]+", " ", AMOUNT.sub(" ", line)).strip(" -–").lower()
        return " ".join(bare.split())
    prices = {}
    for i, line in enumerate(clean):
        name = line.lower() if line.lower() in mine else name_on(line)
        if name not in mine or any(i2 in prices for i2 in mine[name]):
            continue
        price = amount_in(line) if name != line.lower() else None
        for following in clean[i + 1:i + 10]:
            if price:
                break
            low = following.lower()
            if "no sales" in low or low in stops or name_on(following) in stops:
                break
            if low.startswith(FILLER):
                continue
            price = amount_in(following)
        if price:
            for iid in mine[name]:
                prices[iid] = price
    return prices


def enter_prices():
    """Today's prices by hand: paste a list, match it to the inventory,
    show the result, then publish on yes. They become today's point in
    prices.json and the page's current prices."""
    import common
    import settings as cfg
    data = cfg.data_dir()
    inv = json.load(open(os.path.join(data, "inventory.json"), encoding="utf-8"))["items"]
    mine = {}
    for it in inv:
        mine.setdefault(it["name"].lower(), []).append(it["id"])
    try:   # every item name in the game, so the search stops at any item
        from icons import catalog
        all_names = {n.lower() for n in catalog()[0]}
    except Exception:  # noqa: BLE001  (no game files: your own names only)
        all_names = set()
    print("""
  Paste the prices (for example a price site's table copied from the browser,
  or one item per line like "Angel Halo<tab>950k"). Then type END on its own
  line and press Enter.
  Note: if your hourly maplestory.market job runs, it replaces these prices
  within the hour. This is for when you have no key or the market has no data.""")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line)
    hits = parse_price_list(lines, mine, all_names)
    if not hits:
        print("  Found none of your items with a price in that. Nothing changed.")
        return
    missing = [it["name"] for it in inv if it["id"] not in hits]
    value = sum(hits[it["id"]] * it["qty"] for it in inv if it["id"] in hits)
    print("\n  %d of your %d kinds got a price; together they are worth %s mesos:" % (len(hits), len(inv), format(value, ",")))
    for it in sorted((it for it in inv if it["id"] in hits), key=lambda it: -hits[it["id"]] * it["qty"]):
        print("    %-30s %12s  × %d" % (it["name"][:30], format(hits[it["id"]], ","), it["qty"]))
    if missing:
        print("  No price for: " + ", ".join(missing[:12]) + (" …" if len(missing) > 12 else ""))
        print("  (Those keep their last price.)")
    if input("  Publish these as today's prices? [y/N] ").strip().lower() not in ("y", "yes", "j", "ja"):
        print("  Nothing changed.")
        return

    today = datetime.date.today().isoformat()
    prices_file = os.path.join(data, "prices.json")
    pj = json.load(open(prices_file, encoding="utf-8"))
    counts = {it["id"]: it["qty"] for it in inv}
    last = pj["updates"][-1]
    if last["date"] == today:
        last["prices"].update(hits)
        last["manual"] = True
    else:
        pj["updates"].append({"date": today, "prices": {**{i: p for i, p in last["prices"].items() if i in counts}, **hits},
                              "qty": counts, "manual": True})
    common.write_json(prices_file, pj)
    live_file = os.path.join(data, "live.json")
    live = json.load(open(live_file, encoding="utf-8")) if os.path.exists(live_file) else {"items": {}}
    for i, p in hits.items():
        live["items"][i] = {"p": p, "w": "manual"}
    live.update({"updated": int(time.time()), "manual": True, "manual_date": today})
    common.write_json(live_file, live)

    git = ["git", "-C", cfg.WEB]
    subprocess.run(git + ["pull", "-q", "--rebase", "--autostash", cfg.REMOTES[0], "main"])
    subprocess.run(git + ["add", os.path.relpath(prices_file, cfg.WEB), os.path.relpath(live_file, cfg.WEB)], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "MapleStory: prices for %d kinds entered by hand" % len(hits)], check=True)
    for r in cfg.REMOTES:
        subprocess.run(git + ["push", "-q", r, "main"], check=True)
    print("  Published: %d prices entered by hand, today's value of those %s mesos." % (len(hits), format(value, ",")))


DEFAULT_SCREENSHOTS = r"C:\Nexon\Library\maplestorycw\appdata"


def screenshot_folder():
    """The folder the game saves its screenshots in, from settings.json; asked
    for (and saved) the first time, since it differs between computers."""
    path = os.path.join(HERE, "settings.json")
    settings = json.load(open(path, encoding="utf-8"))
    folder = settings.get("screenshot_folder")
    print("""
  Take the screenshots in the game first: open Item Inventory on the Deco tab,
  press Print Screen, scroll down yourself, press Print Screen again, and so on
  to the bottom. Each screenshot should show at least one row from another one.
  Today's screenshots in the folder are read; screenshots of other tabs are skipped.""")
    if folder and os.path.isdir(folder):
        answer = input("  Screenshot folder: %s  (Enter = use it, or type another): " % folder).strip().strip('"')
    else:
        suggestion = DEFAULT_SCREENSHOTS if os.path.isdir(DEFAULT_SCREENSHOTS) else ""
        answer = input("  Where does the game save its screenshots? (the folder with Maple_….jpg)%s: "
                       % (" [%s]" % suggestion if suggestion else "")).strip().strip('"') or suggestion
    new = answer or folder
    if not new or not os.path.isdir(new):
        print("  That folder does not exist: %r" % new)
        return None
    if new != folder:
        settings["screenshot_folder"] = new
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=1)
        print("  Saved; next time it uses this folder.")
    return new


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(HERE, "settings.json")):
        print("No site yet. Run python website_creator.py first.")
        return
    while True:
        print("""
What do you want to do?
  1  Scan the Deco tab in the game (the script scrolls for you)
  2  Read your own screenshots of the Deco tab (the script never touches the game)
  3  Sync from your list (my_items.txt)
  4  Set the mesos : NX rate
  5  Update your site to this version
  6  Enter prices yourself (paste a price list)
  q  Quit""")
        choice = input("> ").strip().lower()
        if choice == "1":
            print("\n  Open Item Inventory in the game and select the Deco tab first.")
            subprocess.run([sys.executable, os.path.join(HERE, "sync.py")])
        elif choice == "2":
            folder = screenshot_folder()
            if folder:
                subprocess.run([sys.executable, os.path.join(HERE, "sync.py"), "--screenshots", folder])
        elif choice == "3":
            subprocess.run([sys.executable, os.path.join(HERE, "sync.py"), "--list", os.path.join(HERE, "my_items.txt")])
        elif choice == "4":
            set_rate()
        elif choice == "5":
            subprocess.run([sys.executable, os.path.join(HERE, "website_creator.py"), "--update"])
        elif choice == "6":
            enter_prices()
        elif choice in ("q", "quit", ""):
            return
        else:
            print("  Pick 1 to 6, or q.")


if __name__ == "__main__":
    main()
