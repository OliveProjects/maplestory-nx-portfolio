"""Syncs the Deco tab to the page.

  python sync.py                   scan, show the difference, ask, publish
  python sync.py --yes             publish without asking
  python sync.py --from <folder>   use an existing scan (view_*.png)
  python sync.py --screenshots <folder>
                                   today's screenshots of the Deco tab that you
                                   took yourself (from_screenshots.py); doesn't
                                   touch the game
  python sync.py --list <file>     the inventory from a text file instead of
                                   the screen (any resolution)

The list file has one line per kind: the count and then the name as the game
writes it, or the id. If two items share a name the script says so and shows
the ids; write the id instead. Empty lines and lines starting with # are
skipped.

    2 Angel Wand
    1 White Label Ring
    1 1112100

Before an automatic run: open Item Inventory on the Deco tab and keep the
game in front. Accept the UAC prompt (the game only takes the mouse from a
program running as administrator), then click in the game if it lost the
focus, and don't touch the mouse until it is done.

Steps:
  1. scan_inventory.py --no-hover (as admin): finds the inventory, checks
     that the Deco tab is selected, scrolls through and saves the views
  2. group_slots.py: groups the slots by icon and counts them
  3. icon_match.py: each group is recognised against the game's own icons
     (icon_library.npz, built from the WZ files with icon_library.py)
  4. the difference from the last sync is shown; nothing is published
     without a yes
  5. deco.json, the icons, inventory.json and the activity log are written,
     today's value point gets the new counts, and everything is committed
     and pushed

The first time (no deco.json yet) everything is the starting holdings: no
lines in the activity log, and the script asks what the items cost on
average.

A group that can't be recognised with certainty stops the publishing.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
import settings as cfg  # noqa: E402
from common import MONTHS, PAGE, WEB, read_deco, write_deco, write_json  # noqa: E402
from fetch_history import TO_MARKET  # noqa: E402
from market_prices import api  # noqa: E402

ACTIVITY = os.path.join(PAGE, "data", "activity.json")
# The ratio between the second best and the best item's error. The right
# item was at least 1.09 in the test (114 slots, 45 kinds, all right).
SAFE_RATIO = 1.04
YES = ("y", "yes", "j", "ja")


def step(nr, text):
    """A heading for each step, so that it shows what is happening (after
    the scan it was otherwise quiet while the items were recognised)."""
    print("\n" + "─" * 60)
    print("STEP %d OF 4 · %s" % (nr, text))
    print("─" * 60)


def progress(text):
    """A line that is written over, only in the window (not in last_sync.txt)."""
    sys.__stdout__.write("\r  " + text.ljust(58))
    sys.__stdout__.flush()


def stop(text):
    """Stops with a message that also ends up in last_sync.txt (SystemExit
    with a text goes to stderr and would have been missing there)."""
    print(text)
    sys.exit(1)


def scan(out):
    step(1, "Reading the game")
    print("  Before this step: open Item Inventory in the game and select the")
    print("  Deco tab, where it usually sits on screen.")
    print("  Accept the UAC prompt, then click in the game within a minute.")
    print("  Don't touch the mouse until it says you can let go.")
    command = ("Start-Process -FilePath '%s' -ArgumentList '\"%s\"','\"%s\"','--no-hover' "
               "-WorkingDirectory '%s' -Verb RunAs -Wait -WindowStyle Minimized"
               % (sys.executable, os.path.join(HERE, "scan_inventory.py"), out, HERE))
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True)
    log = os.path.join(out, "log.txt")
    text = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    lines = text.strip().splitlines()
    if not lines or not lines[-1].endswith(" done"):  # the last line: the scan finished
        stop("The scan did not finish:\n" + (text or "(no log)"))
    print("  Done with the game. You can let go of the mouse and use the computer.")


def recognise(folder):
    """{id: (name, category, count)} in the inventory's order, and a list of
    groups that could not be recognised with certainty."""
    step(2, "Recognising the items")
    print("  Each slot is compared with the game's own icons. This runs on the")
    print("  computer; the game is no longer needed.")
    start = time.time()
    if not any(f.startswith(("view_", "vy_")) for f in os.listdir(folder)):
        stop("  No screenshots in %s: the scan never finished." % folder)
    if not os.path.exists(os.path.join(HERE, "icon_library.npz")):
        stop("icon_library.npz is missing: run python icon_library.py first.")
    progress("Loading the game's icons ...")
    from icon_match import IconLibrary, recognise_group, slots, split_group
    from group_slots import groups
    lib = IconLibrary()
    progress("Grouping the slots by icon ...")
    windows = {(g, c): f for g, c, f in slots(folder)}
    uncertain = []
    deco = read_deco()
    before = {f["id"] for f in deco["items"]} if deco else set()

    def owned(i):
        """The item, or its pixel twin, that the last sync had; else None."""
        known = [t for t in lib.twins.get(i, [i]) if str(lib.ids[t]) in before]
        return known[0] if len(known) == 1 else None

    # Each slot is recognised on its own first, so that a group whose slots
    # clearly show different items can be split (split_group).
    everything = list(groups(folder))
    parts = []
    for nr, grp in enumerate(everything, 1):
        progress("Recognising kind %d of %d ..." % (nr, len(everything)))
        results = {s: lib.recognise(windows[s]) for s in grp["slots"]}
        for part in split_group(grp["slots"], [results[s] for s in grp["slots"]]):
            parts.append((part, [results[s] for s in part]))
    entries = []   # (first slot, id, name, category, count), sorted into the inventory's order below
    for part, results in parts:
        i, error, ratio, second = recognise_group(lib, None, results=results)
        where = "%d from row %d" % (len(part), part[0][0])
        # Two items that look nearly alike (Dollish Pink and Orange Blush,
        # ratio 1.01 on 2026-11-20): if only one of them was in the last
        # sync, it is that one. The change list shows it before publishing.
        if ratio < SAFE_RATIO and second is not None:
            mine = [x for x in (owned(i), owned(second)) if x is not None]
            if len(mine) == 1:
                i, ratio = mine[0], SAFE_RATIO
        # The same icon on several items (White and Blue Label Ring): the one
        # already in the inventory, otherwise the picture can't settle it.
        twins = lib.twins[lib.representative[i]]
        if len(twins) > 1:
            known = owned(i)
            if known is None:
                uncertain.append("%s: same icon as %s; write it in my_items.txt with the id"
                                 % (where, ", ".join("%s (%s)" % (lib.names[t], lib.ids[t]) for t in twins)))
                continue
            i = known
        iid, name, category = str(lib.ids[i]), str(lib.names[i]), str(lib.categories[i])
        if ratio < SAFE_RATIO:
            uncertain.append("%s: probably %s (%s), ratio %.2f" % (where, name, iid, ratio))
            continue
        entries.append((part[0], iid, name, category, len(part)))
    found = {}
    for _, iid, name, category, n in sorted(entries):
        n0, k0, c0 = found.get(iid, (name, category, 0))
        found[iid] = (n0, k0, c0 + n)
    progress("")
    sys.__stdout__.write("\r")
    print("  Done in %d seconds." % round(time.time() - start))
    return found, uncertain


def from_list(path):
    """Like recognise, but from a text file with "count name" or "count id"
    per line. The names are looked up in the game's own files."""
    from icons import catalog
    by_name, by_id = catalog()
    found, unclear = {}, []
    for nr, line in enumerate(open(path, encoding="utf-8-sig"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        count, _, what = line.partition(" ")
        what = what.strip()
        if not count.isdigit() or not what:
            unclear.append("line %d: \"%s\" (write the count first, e.g. 2 Angel Wand)" % (nr, line))
            continue
        if what.isdigit():
            if what not in by_id:
                unclear.append("line %d: no item has the id %s" % (nr, what))
                continue
            iid, (name, category) = what, by_id[what]
        else:
            candidates = by_name.get(what) or next(
                (v for k, v in by_name.items() if k.lower() == what.lower()), [])
            if not candidates:
                unclear.append("line %d: can't find an item called \"%s\"" % (nr, what))
                continue
            if len(candidates) > 1:
                # The icons are saved, so that you can see which is which.
                from icons import icon
                folder = os.path.join(HERE, "candidates")
                os.makedirs(folder, exist_ok=True)
                for k, i in candidates:
                    img = icon(k, i)
                    if img is not None:
                        img.resize((img.width * 3, img.height * 3), 0).save(os.path.join(folder, i + ".png"))
                unclear.append("line %d: several items are called \"%s\", write the id instead: %s "
                               "(the icons are in the folder candidates)"
                               % (nr, what, ", ".join(i for _, i in candidates)))
                continue
            category, iid = candidates[0]
            name = by_id[iid][0]
        n0, k0, c0 = found.get(iid, (name, category, 0))
        found[iid] = (n0, k0, c0 + int(count))
    return found, unclear


def shop_sales():
    """{market id: average price each} for what the characters' shops have
    sold, according to maplestory.market. Empty if the call fails (the
    hourly limit reached, for example); then the sync asks as before."""
    try:
        sold = {}
        for k in cfg.CHARACTERS:
            try:
                answer = api("owners/" + k)
            except urllib.error.HTTPError as e:
                if e.code == 404:  # never seen with a shop
                    continue
                raise
            for s in answer.get("sold_items", []):
                if s["units"]:
                    sold[str(s["item_id"])] = round(s["mesos"] / s["units"])
        return sold
    except Exception as e:  # noqa: BLE001
        print("(could not read the shops' sales: %s)" % e)
        return {}


class Tee:
    """Writes everything to both the window and last_sync.txt, so that the
    run can be read afterwards."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
            st.flush()

    def flush(self):
        for st in self.streams:
            st.flush()


def publish(message):
    git = ["git", "-C", WEB]
    print("\n  Uploading to the site ...")
    subprocess.run(git + ["add", cfg.SUBFOLDER], check=True)
    subprocess.run(git + ["commit", "-m", message], check=True)
    for r in cfg.REMOTES:
        subprocess.run(git + ["push", r, "main"], check=True)
    print("\nDONE. Published: " + cfg.SITE_URL)


def first_time(found, args):
    """The first sync: the starting holdings. No activity, a first price
    entry without prices (the hourly job builds the prices, see the README)
    and the starting holdings in activity.json, with what they cost if you
    know it."""
    yes = "--yes" in args or "--ja" in args
    if not yes and input("\nPublish as the starting holdings? [y/N] ").strip().lower() not in YES:
        stop("Nothing published.")
    average = None
    if not yes:
        answer = input("What did the items cost on average each, in mesos? (e.g. 8k, Enter = don't know) ")
        average = common.parse_amount(answer) if answer.strip() else None
    today = datetime.date.today().isoformat()
    write_deco(today, found)
    import icons
    icons.main(os.path.join(PAGE, "icons"))
    items = common.write_inventory()
    counts = {it["id"]: it["qty"] for it in items}
    write_json(common.PRICES, {"updates": [{"date": today, "prices": {}, "qty": counts}]})
    opening = {"date": today, "month": today[:7], "items": sum(counts.values()), "kinds": len(counts)}
    if average:
        # Estimated: the same price for all. Exact prices per kind can be
        # written into buy_prices ({id: price}) afterwards; spent is not
        # worked out again then.
        opening.update({"spent": average * opening["items"], "spent_estimated": True,
                        "buy_prices": {}, "default_buy_price": average})
    write_json(ACTIVITY, {"opening": opening, "events": []})
    d = datetime.date.today()
    publish("MapleStory: first inventory %d %s" % (d.day, MONTHS[d.month - 1]))


def arg(args, *names):
    """The value after the first of the flags given (English or the older Swedish)."""
    for n in names:
        if n in args:
            return args[args.index(n) + 1]
    return None


def main(args):
    sys.stdout.reconfigure(encoding="utf-8")
    logfile = open(os.path.join(HERE, "last_sync.txt"), "w", encoding="utf-8")
    sys.stdout = Tee(sys.stdout, logfile)
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stderr = Tee(sys.stderr, logfile)
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    yes = "--yes" in args or "--ja" in args
    list_file = arg(args, "--list", "--lista")
    screenshots = arg(args, "--screenshots", "--skarmbilder")
    if list_file:
        found, uncertain = from_list(list_file)
        folder = None
    else:
        if arg(args, "--from", "--fran"):
            folder = arg(args, "--from", "--fran")
        elif screenshots:
            # Today's screenshots that the player took (from_screenshots.py):
            # the script never touches the game.
            step(1, "Reading your screenshots")
            folder = os.path.join(HERE, "last_scan")
            shutil.rmtree(folder, ignore_errors=True)
            import from_screenshots
            from_screenshots.main(screenshots, folder)
        else:
            # Next to the script, not in Temp: there it can be looked at
            # afterwards. Written over on the next run.
            folder = os.path.join(HERE, "last_scan")
            shutil.rmtree(folder, ignore_errors=True)
            os.makedirs(folder)
            scan(folder)
        found, uncertain = recognise(folder)
    step(3, "Comparing with the last sync")
    print("  %d items in %d kinds." % (sum(c for _, _, c in found.values()), len(found)))
    if uncertain:
        print("\nCould not be recognised with certainty:")
        for o in uncertain:
            print("  " + o)
        stop("Nothing published." + (" The scan is kept in %s." % folder if folder else ""))
    if not found:
        stop("No items found. Nothing published.")

    # The hourly job commits the day point itself; pull it first, otherwise
    # the push is rejected and prices.json is written on an old version.
    subprocess.run(["git", "-C", WEB, "pull", "--rebase", "--autostash", "-q", cfg.REMOTES[0], "main"],
                   check=False)
    old = read_deco()
    if not old:
        for _, (name, _, c) in found.items():
            print("  %3d  %s" % (c, name))
        first_time(found, args)
        return

    before = {f["id"]: f for f in old["items"]}
    changes = []
    for iid in list(before) + [i for i in found if i not in before]:
        d = found.get(iid, (0, 0, 0))[2] - before.get(iid, {}).get("count", 0)
        if d:
            name = found[iid][0] if iid in found else before[iid]["name"]
            changes.append((iid, name, d))
    if not changes:
        print("No changes since %s." % old["date"])
        return
    print("\nChanges since %s:" % old["date"])
    for _, name, d in changes:
        print("  %+3d  %s" % (d, name))
    if not yes and input("\nPublish? [y/N] ").strip().lower() not in YES:
        stop("Nothing published.")

    step(4, "Updating your site")
    print("  Icons, the inventory and the activity log ...")
    today = datetime.date.today().isoformat()
    write_deco(today, found)
    import icons
    icons.main(os.path.join(PAGE, "icons"))
    items = common.write_inventory()

    # The activity log: one line per change, with the latest known price.
    data = json.load(open(common.PRICES, encoding="utf-8"))
    latest = {}
    for u in data["updates"]:
        latest.update(u["prices"])
    log = json.load(open(ACTIVITY, encoding="utf-8")) if os.path.exists(ACTIVITY) else {"events": []}
    sold = shop_sales() if any(d < 0 for _, _, d in changes) and not yes else {}
    for iid, name, d in changes:
        row = {"date": today, "id": iid, "name": name, "delta": d, "price": latest.get(iid)}
        # Sold? The page then shows SOLD and "sold for …" instead of REMOVED
        # and the day's market price. If the market saw it sell in a shop,
        # that price is suggested (Enter takes it, n = not sold). Not sold:
        # given away ("given": true) or used ("used": true), both withdrawals.
        if d < 0 and not yes:
            suggestion = sold.get(TO_MARKET.get(iid, iid))
            if suggestion:
                answer = input("Did you sell %s? The shop sold it for %s each. Enter = yes, another price, n = no: "
                               % (name, format(suggestion, ",").replace(",", " ")))
                price = suggestion if not answer.strip() else None if answer.strip().lower() == "n" \
                    else common.parse_amount(answer)
            else:
                answer = input("Did you sell %s? Price each (e.g. 20k), Enter = no: " % name)
                price = common.parse_amount(answer) if answer.strip() else None
            if price:
                row["sold_price"] = price
            else:
                answer = input("  Did you give %s away (g) or use it (u)? Enter = neither: " % name).strip().lower()
                if answer in ("g", "given", "gave"):
                    row["given"] = True
                elif answer in ("u", "used", "use"):
                    row["used"] = True
        # Bought for mesos? Then it counts in the average cost, and the
        # difference from the market price as trading in the month grid.
        # Bought for NX or received: Enter, and the line is neutral.
        if d > 0 and not yes:
            answer = input("Did you buy %s for mesos? Price each, Enter = no: " % name)
            price = common.parse_amount(answer) if answer.strip() else None
            if price:
                row["buy_price"] = price
        log["events"].append(row)
    write_json(ACTIVITY, log)

    # Today's value point gets the new counts. If there is no price entry
    # today, the day before's prices are copied, marked so that the page
    # doesn't read them as a new price movement per item.
    counts = {it["id"]: it["qty"] for it in items}
    if data["updates"] and data["updates"][-1]["date"] == today:
        data["updates"][-1]["qty"] = counts
    else:
        last_prices = data["updates"][-1]["prices"] if data["updates"] else {}
        data["updates"].append({"date": today, "prices": {i: p for i, p in last_prices.items() if i in counts},
                                "qty": counts, "inventory": True})
    write_json(common.PRICES, data)

    d = datetime.date.today()
    short = ", ".join("%+d %s" % (dd, n) for _, n, dd in changes[:4]) + (" …" if len(changes) > 4 else "")
    publish("MapleStory inventory synced %d %s: %s" % (d.day, MONTHS[d.month - 1], short))


if __name__ == "__main__":
    main(sys.argv[1:])
