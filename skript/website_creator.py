"""Creates your own MapleStory portfolio website on GitHub, in one go.

    python website_creator.py            first time: asks a few questions
    python website_creator.py --update   later: new versions of the page,
                                         the scripts and the hourly job

What it does:
  1. creates a public repo on your GitHub account (default name
     maplestory-portfolio) and clones it next to this folder
  2. puts a basic page in it (../sida/index.html, filled in with your
     settings) and the scripts the hourly price job needs (.portfolio/)
  3. adds the hourly job (.github/workflows/prices.yml), which fetches
     prices from maplestory.market and commits them; GitHub runs it for you
  4. stores your API key as the repo secret MAPLESTORY_MARKET_KEY. The key
     never ends up in the page or in git (maplestory.market's terms)
  5. turns on GitHub Pages: the page is at https://<you>.github.io/<repo>/
  6. writes installningar.json here, so Synka.bat pushes to the new repo

You need: a GitHub account, the GitHub CLI (https://cli.github.com, then
`gh auth login` once), git, and your own API key from maplestory.market.
"""
import getpass
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLNINGAR = os.path.join(HERE, "installningar.json")
SERVERSKRIPT = ["installningar.py", "hamta_historik.py", "marknadspriser.py", "delning.py", "actions_steg.py"]
SERVER_IGNORE = "nyckel.txt\nhistorik/\nagare/\ndagssvar/\ntimmar.json\n__pycache__/\n"
STANDARD_WZ = r"C:\Nexon\Library\maplestorycw\appdata\Data"


def kor(args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)


def ut(args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def fraga(text, standard=""):
    svar = input("%s%s: " % (text, " [%s]" % standard if standard else "")).strip()
    return svar or standard


def tolka_belopp(svar):
    """20000, 20,000, 20k or 1.2m -> a whole number; anything else -> None."""
    s = svar.strip().lower().replace(",", "").replace(" ", "")
    faktor = {"k": 1e3, "m": 1e6, "b": 1e9}.get(s[-1:], 1)
    try:
        return int(round(float(s.rstrip("kmb")) * faktor))
    except ValueError:
        return None


def kontrollera_gh():
    if not shutil.which("gh"):
        sys.exit("The GitHub CLI (gh) is missing. Install it from https://cli.github.com and run: gh auth login")
    if not shutil.which("git"):
        sys.exit("git is missing. Install it from https://git-scm.com")
    login = ut(["gh", "api", "user", "-q", ".login"])
    if not login:
        sys.exit("Not logged in to GitHub. Run: gh auth login")
    return login


def lagg_filer(repo_mapp, inst):
    """The page, the server scripts, the workflow and the small files."""
    # The page, filled in from installningar.json (skapa_sida.py does the work).
    kor([sys.executable, os.path.join(HERE, "skapa_sida.py"), "--skriv-over"])
    portfolio = os.path.join(repo_mapp, ".portfolio")
    os.makedirs(portfolio, exist_ok=True)
    for f in SERVERSKRIPT:
        shutil.copy(os.path.join(HERE, f), os.path.join(portfolio, f))
    server_inst = dict(inst, webbrepo="..", git_remotes=["origin"])
    with open(os.path.join(portfolio, "installningar.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(server_inst, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(portfolio, ".gitignore"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SERVER_IGNORE)
    flode = os.path.join(repo_mapp, ".github", "workflows")
    os.makedirs(flode, exist_ok=True)
    shutil.copy(os.path.join(HERE, "mall_workflow.yml"), os.path.join(flode, "prices.yml"))
    rot = os.path.join(repo_mapp, "index.html")
    if not os.path.exists(rot):
        with open(rot, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('<!DOCTYPE html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=%s/">'
                     '<a href="%s/">MapleStory portfolio</a>\n' % (inst["undermapp"], inst["undermapp"]))
    open(os.path.join(repo_mapp, ".nojekyll"), "w").close()
    readme = os.path.join(repo_mapp, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("# %s\n\nMy MapleStory Classic NX cosmetics, valued in mesos like a portfolio: %s\n\n"
                     "Prices from [maplestory.market](https://maplestory.market/). The page and the hourly price job "
                     "were set up with website_creator.py.\n" % (inst["sajtnamn"], inst["sajt_url"]))


def pusha(repo_mapp, meddelande):
    git = ["git", "-C", repo_mapp]
    kor(git + ["add", "-A"])
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        print("Nothing new to push.")
        return
    kor(git + ["-c", "user.name=" + (ut(git + ["config", "user.name"]) or "MapleStory portfolio"),
               "commit", "-q", "-m", meddelande])
    kor(git + ["push", "-q", "-u", "origin", "main"])


def uppdatera():
    if not os.path.exists(INSTALLNINGAR):
        sys.exit("installningar.json is missing: run python website_creator.py first.")
    inst = json.load(open(INSTALLNINGAR, encoding="utf-8"))
    mapp = inst["webbrepo"]
    kor(["git", "-C", mapp, "pull", "-q", "--rebase", "--autostash"])
    lagg_filer(mapp, inst)
    pusha(mapp, "Update the page, the scripts and the hourly job")
    print("Updated: " + inst["sajt_url"])


def skapa():
    login = kontrollera_gh()
    print("Logged in to GitHub as %s.\n" % login)
    if os.path.exists(INSTALLNINGAR):
        print("installningar.json already exists here. To update an existing site, run with --update.")
        if fraga("Create a new site anyway and overwrite installningar.json? (y/N)", "n").lower() not in ("y", "yes"):
            return

    repo = fraga("Name of the new repo", "maplestory-portfolio")
    if ut(["gh", "repo", "view", "%s/%s" % (login, repo), "--json", "name", "-q", ".name"]):
        sys.exit("%s/%s already exists. Pick another name, or use --update for a site you already made." % (login, repo))
    sajtnamn = fraga("Site name (shown at the top of the page)", "%s's MapleStory" % login)
    karaktarer = [k.strip() for k in fraga("Your characters' names, separated by commas (their shop sales are fetched)").split(",") if k.strip()]
    butik = fraga("Which character the shop credit links to", karaktarer[0] if karaktarer else "")
    print("\nYour API key from maplestory.market (Account page). It is stored as an encrypted")
    print("repo secret and in skript/nyckel.txt on this computer, never in the page or in git.")
    print("When you ask for the key, give the page's address below: their daily check reads it.")
    agare = login.lower()   # GitHub Pages addresses are lower case
    sajt_url = ("https://%s.github.io/maplestory/" % agare if repo.lower() == "%s.github.io" % agare
                else "https://%s.github.io/%s/maplestory/" % (agare, repo))
    print("  The page will be at: " + sajt_url)
    nyckel = getpass.getpass("API key (hidden while you type): ").strip()
    if not nyckel:
        sys.exit("No key given. Get one at https://maplestory.market and run again.")
    ref = fraga("Your key's link code (ref) from the Account page")
    tidszon = fraga("Your time zone (where the day ends)", "Europe/Stockholm")
    # The NX rate for the page's NX and $ tiles; change it later with Synka.bat → 3.
    kurs = tolka_belopp(fraga("How many mesos does 1k NX cost in the game now?", "20k")) or 20000
    wz = fraga("The game's Data folder", STANDARD_WZ)
    mapp = fraga("Where to put the site's repo on this computer",
                 os.path.abspath(os.path.join(HERE, "..", "..", repo)))

    print("\nCreating %s/%s ..." % (login, repo))
    kor(["gh", "repo", "create", repo, "--public",
         "--description", "My MapleStory Classic NX cosmetics, valued in mesos like a portfolio"])
    kor(["git", "clone", "-q", "https://github.com/%s/%s.git" % (login, repo), mapp])
    kor(["git", "-C", mapp, "checkout", "-q", "-B", "main"])

    inst = {"karaktarer": karaktarer, "butik": butik, "ref": ref, "sajtnamn": sajtnamn,
            "sajt_url": sajt_url, "tidszon": tidszon, "webbrepo": mapp, "undermapp": "maplestory",
            "git_remotes": ["origin"], "wz_data": wz, "user_agent": sajt_url}
    with open(INSTALLNINGAR, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(inst, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(HERE, "nyckel.txt"), "w", encoding="utf-8") as fh:
        fh.write(nyckel)

    data_mapp = os.path.join(mapp, "maplestory", "data")
    os.makedirs(data_mapp, exist_ok=True)
    with open(os.path.join(data_mapp, "nx_rates.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"usd_per_1k_nx": 1, "rates": [{"from": __import__("datetime").date.today().isoformat(),
                                                  "mesos_per_1k_nx": kurs}]}, fh, indent=1)

    print("Adding the page, the scripts and the hourly job ...")
    lagg_filer(mapp, inst)
    pusha(mapp, "MapleStory portfolio: page, scripts and the hourly price job")

    print("Storing the API key as a repo secret ...")
    kor(["gh", "secret", "set", "MAPLESTORY_MARKET_KEY", "-R", "%s/%s" % (login, repo)], input=nyckel)
    print("Turning on GitHub Pages ...")
    pages = subprocess.run(["gh", "api", "-X", "POST", "repos/%s/%s/pages" % (login, repo),
                            "-f", "build_type=legacy", "-f", "source[branch]=main", "-f", "source[path]=/"],
                           capture_output=True, text=True)
    if pages.returncode and "already" not in (pages.stdout + pages.stderr).lower():
        print("  Could not turn on Pages automatically: %s" % (pages.stderr or pages.stdout).strip())
        print("  Do it by hand: the repo's Settings → Pages → Deploy from a branch → main, / (root).")

    print("""
DONE. Your site: %s
(GitHub Pages can take a few minutes the first time.)

Next:
  1. python ikonbibliotek.py      builds the icon library from the game files (once)
  2. Synka.bat                    the first sync: reads your Deco tab and publishes it
                                  (or write your items in mina_foremal.txt and run Synka lista.bat)
  3. Wait. The hourly job fetches each item's price history, five items per
     hour, and builds the first prices when all are fetched. You can follow
     it under the repo's Actions tab.
After that, run Synka.bat whenever you buy or sell something.
""" % sajt_url)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--update" in sys.argv[1:]:
        uppdatera()
    else:
        skapa()
