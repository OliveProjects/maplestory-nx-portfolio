"""Creates your own MapleStory portfolio website on GitHub, in one go.

    python website_creator.py            first time: asks a few questions
    python website_creator.py --update   later: new versions of the page,
                                         the scripts and the hourly job

What it does:
  1. creates a public repo on your GitHub account (default name
     maplestory-portfolio) and clones it next to this folder
  2. puts a basic page in it (../page/index.html, filled in with your
     settings) and the scripts the hourly price job needs (.portfolio/)
  3. adds the hourly job (.github/workflows/prices.yml), which fetches
     prices from maplestory.market and commits them; GitHub runs it for you
  4. stores your API key as the repo secret MAPLESTORY_MARKET_KEY. The key
     never ends up in the page or in git (maplestory.market's terms)
  5. turns on GitHub Pages: the page is at https://<you>.github.io/<repo>/
  6. creates a PRIVATE repo, <repo>-data, where the hourly job keeps the
     fetched price history, and a deploy key that can write only to it
     (the secret DATA_DEPLOY_KEY). The history must not be public
     (maplestory.market's terms), and the Actions cache can be emptied
  7. writes settings.json here, so Sync.bat pushes to the new repo

You need: a GitHub account, the GitHub CLI (https://cli.github.com, then
`gh auth login` once), git, and your own API key from maplestory.market.
"""
import datetime
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(HERE, "settings.json")
SERVER_SCRIPTS = ["settings.py", "fetch_history.py", "market_prices.py", "share_image.py", "actions_job.py"]
SERVER_IGNORE = "api_key.txt\nhistory\nowners\ndaily\nhours.json\nstore/\n__pycache__/\n"
# The Swedish names the scripts had before 2026-11-16; --update removes them
# from .portfolio/ so the old copies don't linger next to the new ones.
OLD_SERVER_SCRIPTS = ["installningar.py", "installningar.json", "hamta_historik.py", "marknadspriser.py",
                      "delning.py", "actions_steg.py"]
DEFAULT_WZ = r"C:\Nexon\Library\maplestorycw\appdata\Data"
# English key -> the Swedish key versions before 2026-11-18 wrote.
OLD_KEYS = {"characters": "karaktarer", "shop_character": "butik", "site_name": "sajtnamn",
            "site_url": "sajt_url", "time_zone": "tidszon", "site_repo": "webbrepo", "subfolder": "undermapp"}


def run(args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)


def output(args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def ask(text, default=""):
    answer = input("%s%s: " % (text, " [%s]" % default if default else "")).strip()
    return answer or default


def parse_amount(answer):
    """20000, 20,000, 20k or 1.2m -> a whole number; anything else -> None."""
    s = answer.strip().lower().replace(",", "").replace(" ", "")
    factor = {"k": 1e3, "m": 1e6, "b": 1e9}.get(s[-1:], 1)
    try:
        return int(round(float(s.rstrip("kmb")) * factor))
    except ValueError:
        return None


def english_keys(settings):
    """The settings with English keys; a settings.json from an older version
    had Swedish ones."""
    out = dict(settings)
    for en, sv in OLD_KEYS.items():
        if sv in out:
            out.setdefault(en, out[sv])
            del out[sv]
    return out


def write_settings(path, settings):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(settings, fh, ensure_ascii=False, indent=1)


def check_gh():
    if not shutil.which("gh"):
        sys.exit("The GitHub CLI (gh) is missing. Install it from https://cli.github.com and run: gh auth login")
    if not shutil.which("git"):
        sys.exit("git is missing. Install it from https://git-scm.com")
    login = output(["gh", "api", "user", "-q", ".login"])
    if not login:
        sys.exit("Not logged in to GitHub. Run: gh auth login")
    return login


def server_settings(settings):
    """The settings the hourly job needs, for .portfolio/settings.json in the
    public repo. Only what the job uses: not your character names, the
    game's folder or your screenshot folder (which can hold your Windows
    user name), which only the sync on your PC needs."""
    keep = ("ref", "site_name", "site_url", "time_zone", "subfolder", "user_agent")
    return dict({k: settings[k] for k in keep if k in settings}, site_repo="..", git_remotes=["origin"])


def add_files(repo_dir, settings):
    """The page, the server scripts, the workflow and the small files."""
    # The page, filled in from settings.json (make_page.py does the work).
    run([sys.executable, os.path.join(HERE, "make_page.py"), "--overwrite"])
    portfolio = os.path.join(repo_dir, ".portfolio")
    os.makedirs(portfolio, exist_ok=True)
    for f in SERVER_SCRIPTS:
        shutil.copy(os.path.join(HERE, f), os.path.join(portfolio, f))
    for f in OLD_SERVER_SCRIPTS:
        if os.path.exists(os.path.join(portfolio, f)):
            os.remove(os.path.join(portfolio, f))
    write_settings(os.path.join(portfolio, "settings.json"),
                   server_settings(settings))
    with open(os.path.join(portfolio, ".gitignore"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SERVER_IGNORE)
    workflows = os.path.join(repo_dir, ".github", "workflows")
    os.makedirs(workflows, exist_ok=True)
    shutil.copy(os.path.join(HERE, "workflow_template.yml"), os.path.join(workflows, "prices.yml"))
    root = os.path.join(repo_dir, "index.html")
    if not os.path.exists(root):
        with open(root, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('<!DOCTYPE html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=%s/">'
                     '<a href="%s/">MapleStory portfolio</a>\n' % (settings["subfolder"], settings["subfolder"]))
    open(os.path.join(repo_dir, ".nojekyll"), "w").close()
    readme = os.path.join(repo_dir, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("# %s\n\nMy MapleStory Classic NX cosmetics, valued in mesos like a portfolio: %s\n\n"
                     "Prices from [maplestory.market](https://maplestory.market/). The page and the hourly price job "
                     "were set up with website_creator.py.\n" % (settings["site_name"], settings["site_url"]))


def github_repo(repo_dir):
    """"owner/name" of the site repo, from its origin remote."""
    url = output(["git", "-C", repo_dir, "remote", "get-url", "origin"])
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def has_data_repo(site_repo):
    return "DATA_DEPLOY_KEY" in output(["gh", "secret", "list", "-R", site_repo])


def set_up_data_repo(site_repo):
    """The private repo <site repo>-data for the fetched price history, and a
    deploy key that can write only to it, stored as the site repo's secret
    DATA_DEPLOY_KEY. The key is made here and never saved on this computer."""
    if not shutil.which("ssh-keygen"):
        print("  ssh-keygen is missing, so the history stays in the Actions cache. Turn on Windows'")
        print("  OpenSSH Client (Settings → System → Optional features) and run")
        print("  python website_creator.py --update.")
        return False
    data_repo = site_repo + "-data"
    if not output(["gh", "repo", "view", data_repo, "--json", "name", "-q", ".name"]):
        run(["gh", "repo", "create", data_repo, "--private", "--add-readme",
             "--description", "Price history for my MapleStory portfolio (private: maplestory.market's terms)"])
    with tempfile.TemporaryDirectory() as tmp:
        key = os.path.join(tmp, "data_key")
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "maplestory-portfolio hourly job", "-f", key])
        run(["gh", "repo", "deploy-key", "add", key + ".pub", "--allow-write",
             "--title", "Hourly price job (%s)" % site_repo, "-R", data_repo])
        run(["gh", "secret", "set", "DATA_DEPLOY_KEY", "-R", site_repo], input=open(key).read())
    print("  The price history is kept in your private repo %s." % data_repo)
    return True


def push(repo_dir, message):
    git = ["git", "-C", repo_dir]
    run(git + ["add", "-A"])
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        print("Nothing new to push.")
        return
    run(git + ["-c", "user.name=" + (output(git + ["config", "user.name"]) or "MapleStory portfolio"),
               "commit", "-q", "-m", message])
    run(git + ["push", "-q", "-u", "origin", "main"])


def update():
    if not os.path.exists(SETTINGS):
        sys.exit("settings.json is missing: run python website_creator.py first.")
    old = json.load(open(SETTINGS, encoding="utf-8"))
    settings = english_keys(old)
    if settings != old:
        write_settings(SETTINGS, settings)
        print("settings.json now has English keys.")
    folder = settings["site_repo"]
    run(["git", "-C", folder, "pull", "-q", "--rebase", "--autostash"])
    add_files(folder, settings)
    push(folder, "Update the page, the scripts and the hourly job")
    site_repo = github_repo(folder)
    if site_repo and shutil.which("gh") and not has_data_repo(site_repo):
        print("\nThe hourly job keeps the fetched price history in the Actions cache, which GitHub")
        print("can empty. It can keep it in a private repo on your GitHub instead (%s-data)." % site_repo)
        if ask("Make the private data repo? (Y/n)", "y").lower() in ("y", "yes"):
            set_up_data_repo(site_repo)
    print("Updated: " + settings["site_url"])


def create():
    login = check_gh()
    print("Logged in to GitHub as %s.\n" % login)
    if os.path.exists(SETTINGS):
        print("settings.json already exists here. To update an existing site, run with --update.")
        if ask("Create a new site anyway and overwrite settings.json? (y/N)", "n").lower() not in ("y", "yes"):
            return

    repo = ask("Name of the new repo", "maplestory-portfolio")
    if output(["gh", "repo", "view", "%s/%s" % (login, repo), "--json", "name", "-q", ".name"]):
        sys.exit("%s/%s already exists. Pick another name, or use --update for a site you already made." % (login, repo))
    site_name = ask("Site name (shown at the top of the page)", "%s's MapleStory" % login)
    characters = [k.strip() for k in ask("Your characters' names, separated by commas (when an item is gone, the sync "
                                         "looks up what their shops sold it for)").split(",") if k.strip()]
    print("\nYour API key from maplestory.market (Account page). It is stored as an encrypted")
    print("repo secret and in scripts/api_key.txt on this computer, never in the page or in git.")
    print("When you ask for the key, give the page's address below: their daily check reads it.")
    owner = login.lower()   # GitHub Pages addresses are lower case
    site_url = ("https://%s.github.io/maplestory/" % owner if repo.lower() == "%s.github.io" % owner
                else "https://%s.github.io/%s/maplestory/" % (owner, repo))
    print("  The page will be at: " + site_url)
    key = getpass.getpass("API key (hidden while you type): ").strip()
    if not key:
        sys.exit("No key given. Get one at https://maplestory.market and run again.")
    ref = ask("Your key's link code (ref) from the Account page")
    time_zone = ask("Your time zone (where the day ends)", "Europe/Stockholm")
    # The NX rate for the page's NX and $ tiles; change it later with Sync.bat → 4.
    rate = parse_amount(ask("How many mesos does 1k NX cost in the game now?", "20k")) or 20000
    wz = ask("The game's Data folder", DEFAULT_WZ)
    folder = ask("Where to put the site's repo on this computer",
                 os.path.abspath(os.path.join(HERE, "..", "..", repo)))

    print("\nCreating %s/%s ..." % (login, repo))
    run(["gh", "repo", "create", repo, "--public",
         "--description", "My MapleStory Classic NX cosmetics, valued in mesos like a portfolio"])
    run(["git", "clone", "-q", "https://github.com/%s/%s.git" % (login, repo), folder])
    run(["git", "-C", folder, "checkout", "-q", "-B", "main"])

    settings = {"characters": characters, "ref": ref, "site_name": site_name,
                "site_url": site_url, "time_zone": time_zone, "site_repo": folder, "subfolder": "maplestory",
                "git_remotes": ["origin"], "wz_data": wz, "user_agent": site_url}
    write_settings(SETTINGS, settings)
    with open(os.path.join(HERE, "api_key.txt"), "w", encoding="utf-8") as fh:
        fh.write(key)

    data_dir = os.path.join(folder, "maplestory", "data")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "nx_rates.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"usd_per_1k_nx": 1, "rates": [{"from": datetime.date.today().isoformat(),
                                                  "mesos_per_1k_nx": rate}]}, fh, indent=1)

    print("Adding the page, the scripts and the hourly job ...")
    add_files(folder, settings)
    push(folder, "MapleStory portfolio: page, scripts and the hourly price job")

    print("Storing the API key as a repo secret ...")
    run(["gh", "secret", "set", "MAPLESTORY_MARKET_KEY", "-R", "%s/%s" % (login, repo)], input=key)
    print("Making the private repo for the price history ...")
    set_up_data_repo("%s/%s" % (login, repo))
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
  1. In the game, open Item Inventory on the Deco tab and take screenshots
     (Print Screen), scrolling a few rows between them, down to the bottom.
  2. Double-click Sync.bat and pick 2 (your screenshots). The first time it
     also builds the icon library from the game's files, about a minute.
  3. Wait. The hourly job fetches each item's price history, five items an
     hour, and builds the first prices when all are fetched (about 9 hours
     for 45 kinds). You can follow it under the repo's Actions tab.
After that, run Sync.bat whenever you buy, sell, give away or use something.
""" % site_url)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--update" in sys.argv[1:]:
        update()
    else:
        create()
