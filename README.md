# MapleStory NX portfolio in mesos

Values the NX cosmetics in your MapleStory Classic **Deco tab** like a stock portfolio: in mesos, at market prices from [maplestory.market](https://maplestory.market), on your own website on GitHub.

> This is the same chain that runs [oliveprojects.eu/maplestory](https://oliveprojects.eu/maplestory/), made general so that anyone can run it, with a deliberately plain page. [oliveprojects.eu/maplestory/free](https://oliveprojects.eu/maplestory/free/) shows what this page looks like with real data.

The page shows:
- the portfolio's value, updated every hour, and a chart of it over time (in mesos, in % and in dollars)
- unrealised and realised return against what you paid
- every item with its price, value, share of the total, return and change over 24 hours
- an activity log of what you bought, sold, gave away or used, and what your shops have sold
- a share image with the value and the week's chart, shown when the link is posted in for example Discord

**In short, what you do:** install four free programs, ask maplestory.market for a free API key, run one setup script, then take screenshots of your Deco tab and double-click `Sync.bat` whenever your inventory changes. GitHub does the rest every hour, for free.

## How it fits together

```
Your PC (Windows, with the game)            Your GitHub account (free)
───────────────────────────────────         ─────────────────────────────────────────────
Sync.bat                                    REPO (public): your website
  reads your Deco tab                         maplestory/          the page and its data
  - from your screenshots, or                 .portfolio/          the price scripts
  - by scrolling it itself, or     ──push──▶  .github/workflows/   the hourly price job
  - from a list you write                     GitHub Pages shows the page
  recognises each item from the
  game's own icons, asks before             GitHub Actions, every hour at xx:05:
  publishing, and pushes the                  fetches prices from maplestory.market
  inventory to REPO                           with your key, commits the new values to
                                              REPO, keeps the fetched history in
                                            REPO-data (private): the price history
```

No server of your own is needed.

## What you need

| | Why | Where |
|---|---|---|
| **Windows** with **MapleStory Classic** installed | the item names and icons are read from the game's own files, even when you use screenshots | |
| **Python 3.10 or newer** | runs the scripts. Tick "Add python.exe to PATH" when installing | [python.org](https://www.python.org/downloads/) |
| **Git** | sends your inventory to your repo | [git-scm.com](https://git-scm.com/downloads) |
| `ssh-keygen` | used once, to make the key for the private data repo. Windows 10 and 11 already have it (the OpenSSH Client) | |
| **A GitHub account** and the **GitHub CLI** | your website and the hourly job live there. After installing the CLI, run `gh auth login` once | [github.com](https://github.com), [cli.github.com](https://cli.github.com) |
| **Your own maplestory.market API key** | the prices. Free, 6 calls an hour | see step 1 |

Everything here is free. Your site repo is public (GitHub Pages and Actions are free for public repos); the data repo is private and runs nothing.

## What the scripts do, and don't do

Be sure you are fine with this before you start.

**On your computer**
- **Reading your Deco tab, three ways (you choose each time):**
  1. **Your own screenshots** (menu option 2): the script only reads image files the game saved when you pressed Print Screen. It never touches the game and needs no admin rights.
  2. **Scrolling it itself** (menu option 1): the script asks for administrator rights (Windows shows a UAC prompt), then moves your mouse over the Deco tab, sends scroll-wheel steps to the game window and takes screenshots of it. Nothing else: no keyboard input, no clicks, no reading of the game's memory, no changes to its files. It stops at once if another window comes in front or the game isn't at 3840×2160. If you are unsure whether sending mouse input to the game is fine under Nexon's terms, use option 2 or 3 instead.
  3. **A list you write** (menu option 3): no game, no screenshots.
- **The game's files** (`Data` in the game folder) are only read, to get item names and icons. They are never changed.
- **Files the scripts write** stay in the `scripts` folder (`settings.json`, `api_key.txt`, `deco.json`, `icon_library.npz`, `last_scan/`, `last_sync.txt`) and in the copy of your site repo. `api_key.txt`, `settings.json` and your inventory files are in `.gitignore` and never pushed from this folder.

**Over the network**
- **GitHub**, through `git` and the GitHub CLI: creating your repos, pushing your inventory.
- **maplestory.market**, with your key:
  - every hour from GitHub Actions: the price history of five of the items you own (five calls), and your characters' shops about once a day;
  - from your PC during a sync, only when something is gone from your inventory: one call per character to see what your shops sold, to suggest the price.
  The scripts identify themselves with your page's address as User-Agent.
- Nothing else. No analytics, no other price sites.

**What becomes public**
- Your site repo and page: your Deco inventory, what you paid, sold and gave away, the value over time, your character names (for the shop sales) and your key's link code (which maplestory.market wants in every link to them).
- Never public: the API key (an encrypted repo secret, and `api_key.txt` on your PC), and the fetched price history (your private data repo; maplestory.market's terms don't allow republishing their data in bulk).

## 1. The API key

1. Make an account on https://maplestory.market and ask for a key on the Account page. Give your page's address: by default `https://YOURNAME.github.io/maplestory-portfolio/maplestory/` (YOURNAME is your GitHub username in lower case). Their daily check fetches that page and looks for the credit. A person approves keys, so it can take a while.
2. Read the terms: https://maplestory.market/docs/api/terms. In short, and all of it is already handled:
   - The credit "Prices from maplestory.market" stays on the page and links to them with your key's link code (`?ref=…`). Each item links to its page on maplestory.market.
   - The key is never in a web page or in a public repo.
   - No republishing of their data in bulk: the page shows prices only for what you own, plus totals and percentages, and the fetched history stays in your private data repo.
3. Note the key and your link code (`ref`) from the Account page. One key per project: don't reuse a key you use for something else.

## 2. Set up (once, about 10 minutes)

Download this repo (Code → Download ZIP and unpack it, or `git clone`), open a terminal in the `scripts` folder and run:

```
pip install -r requirements.txt
python website_creator.py
```

`website_creator.py` asks:

| Question | Example |
|---|---|
| name of the new repo | `maplestory-portfolio` |
| the site's name, shown at the top of the page | `My MapleStory` |
| your characters' names, comma-separated (their shop sales are fetched) | `MyMain, MyMule` |
| which character the shop credit links to | `MyMain` |
| your API key (hidden while you type) and its link code | |
| your time zone, where your day ends | `Europe/Stockholm` |
| how many mesos 1k NX costs in the game now | `20k` |
| the game's `Data` folder | `C:\Nexon\Library\maplestorycw\appdata\Data` |
| where to put your site's repo on this computer | next to this folder |

Then it, by itself:
1. creates the public repo `REPO` on your GitHub account and clones it
2. puts the page, the price scripts and the hourly job in it, and pushes
3. stores the API key as the repo secret `MAPLESTORY_MARKET_KEY`
4. creates the private repo `REPO-data` and a deploy key that can write only to it (the secret `DATA_DEPLOY_KEY`)
5. turns on GitHub Pages: the page is at `https://YOURNAME.github.io/REPO/maplestory/`
6. writes `settings.json` and `api_key.txt` in the `scripts` folder

## 3. The first sync

What you own the first time becomes your starting holdings. The script asks what the items cost on average each; that is used for the return and can be refined later (see below). The first sync also builds the icon library from the game's files, about a minute.

**From your own screenshots** (recommended: the script never touches the game):
1. In the game, open **Item Inventory** (key I) and select the **Deco** tab.
2. Press **Print Screen**. Scroll down yourself, a few rows, and press Print Screen again, so that each screenshot shows at least one row from the one before. Go on to the bottom of the tab.
3. Double-click `Sync.bat` and pick **2**. The first time it asks where the game saves its screenshots (the folder with `Maple_YYMMDD_HHMMSS.jpg`; it suggests the game's usual folder) and remembers it.

The script reads today's screenshots in that folder, skips the ones of other tabs, and fits them together by their rows, so a row in several screenshots counts once. A tooltip or the mouse pointer over a slot in one screenshot is filled in from the others. Any resolution works, 16:9, 16:10 or 4:3: the game draws its interface larger the taller the window is, so the script measures the inventory's size in each screenshot. Tested on ten resolutions from 3840×2160 down to 800×600, with every slot recognised right in all ten. The higher the resolution, the more certain the recognition, so use a high one if you can.

**By scrolling it itself** (only with the game at 3840×2160):
1. Open **Item Inventory** on the **Deco** tab.
2. Double-click `Sync.bat` and pick **1**.
3. Accept the UAC prompt, click in the game within a minute, and don't touch the mouse until it says you can let go.

**From a list:**
1. Write your inventory in `my_items.txt`, one line per kind: the count and the name as the game writes it, or the item's id.
   ```
   2 Angel Wand
   1 1112100
   ```
2. Double-click `Sync.bat` and pick **3** (or double-click `Sync list.bat`).

**Questions the sync may ask:**
- Some items have exactly the same icon (White Label Ring and Blue Label Ring, for example). The first time, the sync lists them and asks which one it is; after that it remembers. In a list, several items can share a name (Cat Hat): the script shows their ids and saves their icons in the `candidates` folder, so write the id instead.
- Before anything is published it shows what it found, or what changed, and asks. Read the list: if something looks wrong, answer no.

The page appears at once, but without prices until the hourly job has fetched them (step 4).

## 4. The hourly price job

It runs by itself on GitHub every hour at xx:05. The repo's **Actions** tab shows each run.

- **The first time** it fetches every item's price history, five items an hour (the key allows 6 calls an hour; one is left for the sync). That takes the number of kinds you own divided by five, in hours: about nine hours for 45 kinds. Then it builds the prices for the past week, as far back as the API's history goes, and the page fills in.
- **After that** it refreshes five items an hour, so every price is at most a few hours old, updates the current value and the hourly chart, and after midnight saves yesterday's value as a daily point.

You can start a run by hand under Actions → Prices → Run workflow.

### How prices are set

The price is a median, never an average, so one odd sale can't move it. maplestory.market records for every hour what sold and at what median price. An item's price is the median of those hours, weighted by units sold, over the last 24 hours, or over the last 3 or 7 days for an item that sells less; no single hour counts for more than a quarter. With no sales in a week, the price is the lower of the day before's price and 85 % of what sellers ask. If the prices of well-selling items move more than 40 % in a day, that day isn't saved as a daily point and the run shows an error in the Actions tab, so that a fault in the data doesn't end up in your history unnoticed.

The data comes from what maplestory.market sees in the game's shops, and can have gaps: in November 2026 it recorded almost no sales for two weeks, and the prices then froze until it saw sales again.

### Where your data is kept

Everything stays on your own GitHub account:

| What | Where | Public? |
|---|---|---|
| The page, your inventory, the daily prices, the hourly value | your site repo (`maplestory/data/`), committed every hour | yes, it is your page |
| The fetched hourly price history from maplestory.market | your private repo `REPO-data`, pushed after every run | no |
| The API key | the repo secret `MAPLESTORY_MARKET_KEY` | no |

The API only gives a week back, so the job adds every hour it fetches to the data repo, and the history grows from the day you start. If you set up your site before the data repo existed, `python website_creator.py --update` offers to make it and moves what the Actions cache holds into it. Without it the history stays in the Actions cache, which GitHub empties after a week without runs.

## Day to day

Double-click `Sync.bat`. It asks what you want to do:

```
What do you want to do?
  1  Scan the Deco tab in the game (the script scrolls for you)
  2  Read your own screenshots of the Deco tab (the script never touches the game)
  3  Sync from your list (my_items.txt)
  4  Set the mesos : NX rate
  5  Update your site to this version
  6  Enter prices yourself (paste a price list)
  q  Quit
```

- **1, 2 or 3** after you bought, sold, gave away or used something. The sync shows what changed and asks:
  - **gone:** did you sell it, and for what? If the market saw your shop sell it, that price is suggested. If not: did you give it away (g) or use it (u)? Both count as taking it out, neither gain nor loss.
  - **new:** what you paid in mesos. Press Enter if you bought it for NX or got it.
- **4** when the game's rate moves: how many mesos 1k NX costs, and what 1k NX costs in dollars from Nexon. The page's NX and $ tiles and the $ chart use it, and every day keeps the rate it had.
- **5** after you downloaded a newer version of this repo: it updates the page, the scripts and the hourly job in your site repo.
- **6** to enter today's prices yourself, for when you have no key or the market has no data: paste a price list (any layout; every line that is one of your items is a starting point, and its price is the first mesos amount after it) and end with a line saying `END`. The script lists what got a price and publishes only if you say yes. The hourly job replaces these prices when it has its own.

**After a game update** with new items, nothing is needed: the sync notices that the game's files are newer than its icon library and builds it again (about a minute), so the new items are recognised. An item the library doesn't have would otherwise be read as the nearest one it has, often another colour of the same piece.

### Exact purchase prices afterwards (optional)

Under `opening` in `maplestory/data/activity.json` you can write what each kind cost, by item id:
```json
"buy_prices": { "1112100": 110000, "1702004": 15000 }
```
Kinds missing there get `default_buy_price`. Also change `spent` to the new total.

### Changing the page

The page is `maplestory/index.html` in your site repo, a plain file with its colours at the top. Restyle it as you like; keep the credit to maplestory.market. `python website_creator.py --update` replaces the page, so keep your own copy if you have changed it.

## Stopping or removing it

- **Pause the prices:** in your site repo, Actions → Prices → ⋯ → Disable workflow.
- **Remove everything:** delete the repos `REPO` and `REPO-data` on GitHub (Settings → Delete this repository), revoke the key on your maplestory.market Account page, and delete the `scripts` folder on your PC.

## The folders

```
scripts/   everything that runs on your PC, plus the price scripts that
           website_creator.py copies to your site repo
page/      the page template (index.html)
```

| Script | What it does |
|---|---|
| `website_creator.py` | creates your site repo, the data repo, the page, the hourly job and the secrets; `--update` brings them up to date |
| `menu.py` (`Sync.bat`) | the menu: scan, screenshots, list, NX rate, update, prices by hand |
| `from_screenshots.py` | reads the Deco tab from your own screenshots |
| `scan_inventory.py` | finds the inventory in the game window and scrolls through it (option 1) |
| `sync.py` | recognises the items, shows the changes, publishes them |
| `group_slots.py`, `icon_match.py` | group the slots by icon and match them against the game's icons |
| `icon_library.py`, `icons.py` | read the icons and names from the game's files |
| `fetch_history.py` | fetches each item's hourly price history from maplestory.market |
| `market_prices.py` | turns the history into prices |
| `share_image.py` | the share image and the page's Open Graph tags |
| `actions_job.py` | the hourly job on GitHub Actions |
| `run_hourly.sh` | the same job on your own Linux server, if you prefer that to Actions |

## If something goes wrong

- **"No time zone found with key …":** run `pip install -r requirements.txt` again (it installs `tzdata`, which Windows needs).
- **"ssh-keygen is missing":** turn on Windows' OpenSSH Client (Settings → System → Optional features → Add a feature), then run `python website_creator.py --update` to make the private data repo.
- **"Could not be recognised with certainty":** nothing was published. Take the screenshots again with the whole Deco grid visible (a higher resolution helps), or use the list. The cut-out views are kept in `last_scan/` (`view_00.png`, `view_06.png` …) so you can look at them.
- **"screenshot(s) … fit none of the others":** you scrolled too far between two screenshots. Scroll a few rows at a time, so each shows at least one row from another.
- **A new item counted as one you already have:** the sync checks each slot on its own and splits a group whose slots clearly show different items, and when two items look nearly alike it picks the one you already own. Both show in the change list before anything is published, so read it.
- **"the game's client area is … but the grid is measured in 3840x2160":** option 1 only works at that size. Use your screenshots (option 2) or the list (option 3).
- **"the game is no longer in front, stopping":** another window came on top during option 1. Keep the game in front and don't touch the mouse.
- **The page has no prices after a day:** open the Actions tab. "The secret MAPLESTORY_MARKET_KEY is missing" means the key wasn't stored: add it under Settings → Secrets and variables → Actions. A red run shows its error there.
- **429 from the API:** the hour's calls are used up. The job tries again the next hour.
- **An item has another id on the market than in the game:** add it to `TO_MARKET` in `fetch_history.py` and to `MARKET_ID` in the page. White Label Ring is already there.
