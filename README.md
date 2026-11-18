# MapleStory NX portfolio in mesos

Values the NX cosmetics in your MapleStory Classic **Deco tab** like a stock portfolio: in mesos, at market prices from [maplestory.market](https://maplestory.market), on your own website.

> **Version:** this is the version that fetches prices from maplestory.market's API with your own API key. It is the code behind [oliveprojects.eu/maplestory](https://oliveprojects.eu/maplestory/) as it was until November 2026, made general so that anyone can run it. The page here is deliberately plain.

The page shows:
- the portfolio's value, updated every hour, and a chart of it over time
- unrealised and realised return against what you paid
- every item with its price, value, share of the total, return and change over 24 hours
- an activity log of what you bought and sold, and what your shops have sold
- a share image with the value and the week's chart, shown when the link is posted in for example Discord

## How it fits together

```
Your PC (Windows, with the game)          GitHub (free)
─────────────────────────────────          ─────────────────────────────────────────
Sync.bat                                  your site repo, e.g. maplestory-portfolio
  reads your Deco tab from the screen  ──▶   maplestory/        the page and its data
  (or from a text list), recognises          .portfolio/        the price scripts
  each item from the game's own icons,       .github/workflows/ the hourly price job
  and pushes the inventory to your repo    GitHub Pages shows the page
                                           GitHub Actions runs the price job every hour:
                                             fetches prices from maplestory.market
                                             with your key (a repo secret) and commits
                                             the new values
```

You only need a GitHub account and your own API key. No server: GitHub runs the hourly job.

## What you need

- **Windows** with **MapleStory Classic** installed. The icons and item names are read from the game's own files.
- **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/)). Tick "Add python.exe to PATH" when installing.
- **Git** ([git-scm.com](https://git-scm.com/downloads)).
- **A GitHub account** and the **GitHub CLI** ([cli.github.com](https://cli.github.com)). After installing, run `gh auth login` once and log in.
- **Your own API key from maplestory.market**, see below. It is free and allows 6 calls an hour.
- Optional: the game in 3840×2160 if the inventory should be read from the screen. Otherwise you write a list, which works in any resolution.

## 1. The API key

1. Make an account on https://maplestory.market and ask for a key on the Account page. Give your page's address: by default `https://YOURNAME.github.io/maplestory-portfolio/maplestory/` (YOURNAME is your GitHub username). Their daily check fetches that page and looks for the credit.
2. Read the terms: https://maplestory.market/docs/api/terms. In short, and all of it is already handled:
   - The credit "Prices from maplestory.market" stays on the page and links to them with your key's link code (`?ref=…`). Each item links to its page on maplestory.market.
   - The key is never in a web page or in a public repo. Here it is an encrypted repo secret, and a file on your PC that git ignores.
   - No republishing of their data in bulk. The page only publishes daily prices for what you own, totals and percentages. The fetched hourly history stays in the Actions cache and is never committed.
3. Note the key and your link code (`ref`) from the Account page. One key per project: don't reuse a key you use for something else.

## 2. Set up

Download this repo (Code → Download ZIP, or `git clone`) and open a terminal in the `scripts` folder:

```
pip install -r requirements.txt
python website_creator.py
python icon_library.py
```

- **`website_creator.py`** asks a few questions (repo name, site name, your characters, the API key, the link code, your time zone) and then:
  - creates a public repo on your GitHub account and clones it next to this folder
  - puts the page, the price scripts and the hourly job in it, and pushes
  - stores the key as the repo secret `MAPLESTORY_MARKET_KEY`
  - turns on GitHub Pages, so the page is at `https://YOURNAME.github.io/REPO/maplestory/`
  - writes `settings.json` here, so that the sync knows where to push
- **`icon_library.py`** builds the icon library from the game files. It takes a few seconds. Run it again after a big game update.

## 3. The first sync

What you own the first time becomes your starting holdings. The script asks what the items cost on average each; that is used for the return and can be refined later (see below).

**From the screen** (3840×2160 only):
1. Open **Item Inventory** in the game and select the **Deco** tab.
2. Double-click `Sync.bat` and pick **1**.
3. Accept the UAC prompt (the game only takes mouse input from a program running as administrator), click in the game within a minute, and don't touch the mouse until it says you can let go.

The script finds the inventory wherever it sits in the window and scrolls through the tab. It then recognises every item from the game's own icons, shows what changed, and asks before it publishes. In another resolution it stops at once instead of clicking in the wrong place.

**From your own screenshots** (the script never touches the game, no admin rights):
1. In the game, open **Item Inventory** on the **Deco** tab and press **Print Screen**.
2. Scroll down yourself and press Print Screen again, so that each screenshot shows at least one row from another one. Go on to the bottom of the tab.
3. Double-click `Sync.bat` and pick **2**. The first time it asks where the game saves its screenshots (the folder with `Maple_YYMMDD_HHMMSS.jpg`; it suggests the game's usual folder) and remembers it.

The script reads the day's screenshots in that folder, skips the ones of other tabs, finds the inventory in each (any 16:9 resolution), and fits them together by their rows, so a row in several screenshots counts once. Where a row is in several screenshots, each pixel is the median of them, so a tooltip in one screenshot goes away; the game's mouse pointer is found and left out too. Tested 2026-11-18 on 17 screenshots in two rounds, scrolled back and forth: 112 items in 47 kinds, the same as the scan.

**From a list** (always works):
1. Write your inventory in `my_items.txt`, one line per kind with the count and the name as the game writes it:
   ```
   2 Angel Wand
   1 1112100
   ```
2. Double-click `Sync.bat` and pick **3** (or double-click `Sync list.bat`).

If several items share a name, for example Cat Hat or White Label Ring, the script shows their ids and saves their icons in the `candidates` folder. Write the id on the line instead of the name.

The page appears straight away, but without prices until the hourly job has fetched them.

## 4. The hourly price job

It runs by itself on GitHub every hour (the repo's **Actions** tab shows each run).

- **The first time** it fetches every item's price history, five items an hour (the key's limit is 6 calls an hour; one is left for the sync). With 45 kinds that takes about nine hours. Then it builds the prices for the past week, as far back as the API's history goes, and the page fills in.
- **After that** it refreshes five items an hour, so every price is at most a few hours old, writes the current value and the hourly chart, and after midnight saves yesterday's value as a daily point.

You can start a run by hand under Actions → Prices → Run workflow.

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
  - **new:** what you paid. Press Enter if you bought it for NX or got it.
- **4** when the game's rate moves: how many mesos 1k NX costs, and what 1k NX costs in dollars from Nexon. The page's NX and $ tiles and the $ chart use it, and every day keeps the rate it had, so the $ line can differ from the mesos line.
- **5** after you downloaded a newer version of this repo.
- **6** to enter today's prices yourself: paste a price list and end with a line saying `END`. The layout does not matter much: every line that is one of your items is a starting point, and its price is the first mesos amount after it (`950K`, `1.1M`, `8,999`); percentages, NX prices, sales counts and lines like "Cash Shop" are skipped, and the search stops at the next item name or "No sales". A name and a price on one line work too (`Angel Halo 950k`). The script lists what got a price and the total, and publishes only if you say yes. If the hourly maplestory.market job runs, it replaces these prices within the hour, so this is for when you have no key or the market has no data.

### Exact purchase prices afterwards (optional)

Under `opening` in `maplestory/data/activity.json` you can write what each kind cost, by item id:
```json
"buy_prices": { "1112100": 110000, "1702004": 15000 }
```
Kinds missing there get `default_buy_price`. Also change `spent` to the new total.

### Changing the page

The page is `maplestory/index.html` in your site repo, a plain file with its colours at the top. Restyle it as you like; keep the credit to maplestory.market. To get a newer version of the page, the scripts and the job from this repo, run `python website_creator.py --update`. It replaces the page, so keep your own copy if you have changed it.

## The folders

```
scripts/   everything that runs on your PC, plus the price scripts that
          website_creator.py copies to your site repo
page/     the page template (index.html)
```

The main scripts:

| Script | What it does |
|---|---|
| `website_creator.py` | creates your site repo, the page, the hourly job and the secret |
| `menu.py` (`Sync.bat`) | the menu: scan, screenshots, list, NX rate, update, prices by hand |
| `from_screenshots.py` | reads the Deco tab from your own screenshots (menu option 2) |
| `sync.py` | reads the Deco tab, recognises the items, publishes the changes |
| `scan_inventory.py` | finds the inventory in the game window and scrolls through it |
| `group_slots.py`, `icon_match.py` | group the slots by icon and match them against the game's icons |
| `icon_library.py`, `icons.py` | read the icons and names from the game's WZ files |
| `fetch_history.py` | fetches each item's hourly price history from maplestory.market |
| `market_prices.py` | turns the history into prices: the median of what actually sold |
| `share_image.py` | the share image and the page's Open Graph tags |
| `actions_job.py` | the hourly job on GitHub Actions |
| `run_hourly.sh` | the same job on your own Linux server, if you prefer that to Actions |

## If something goes wrong

- **"the game's client area is … but the grid is measured in 3840x2160":** use your own screenshots or the list (`Sync.bat`, options 2 and 3), or re-measure the sizes at the top of `scan_inventory.py`, `tab_template.png` and `SCALE` in `icon_match.py`.
- **"Could not be recognised with certainty":** nothing was published. Use the list, or run again with the inventory fully visible. The scan's views are kept in `last_scan/` (`view_00.png`, `view_06.png` …) so you can look at them.
- **"the game is no longer in front, stopping":** another window came on top. Keep the game in front and don't touch the mouse.
- **The page has no prices after a day:** open the Actions tab. "The secret MAPLESTORY_MARKET_KEY is missing" means the key was not stored: add it under Settings → Secrets and variables → Actions. A red run shows its error there.
- **429 from the API:** the hour's calls are used up. The job tries again next hour.
- **An item has another id on the market than in the game:** add it to `TO_MARKET` in `fetch_history.py` and to `MARKET_ID` in the page. White Label Ring is already there.
- **Never fetch from other price sites automatically** without reading their terms.
