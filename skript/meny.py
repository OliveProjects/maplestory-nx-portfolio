"""What Synka.bat shows: a menu of what you can do.

  1  Scan the Deco tab in the game        (synka.py)
  2  Sync from your list                  (synka.py --lista mina_foremal.txt)
  3  Set the mesos : NX rate              (data/nx_rates.json on your site)
  4  Update your site to this version     (website_creator.py --update)

The rate is how many mesos 1k NX costs in the game right now, plus what
1k NX costs in dollars from Nexon. The page's NX and $ tiles and the $
chart use it. Each change is saved with today's date, so the $ chart
values every day at the rate that applied then.

    python meny.py
"""
import datetime
import json
import os
import subprocess
import sys

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
        elif val in ("q", "quit", ""):
            return
        else:
            print("  Pick 1, 2, 3, 4 or q.")


if __name__ == "__main__":
    main()
