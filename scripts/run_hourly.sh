#!/bin/bash
# The MapleStory prices on your own server, every hour. In crontab (crontab -e):
#   5 * * * * /home/YOURNAME/maplestory/scripts/run_hourly.sh >> /home/YOURNAME/maplestory/log.txt 2>&1
#
#  1. fetch_history.py --rotate: fetches the hourly history of the five items
#     fetched longest ago, and the characters' shops once a day. The sixth
#     call of the hour is left for the sync on your computer.
#  2. market_prices.py --live: works out the prices from what was fetched and
#     writes live.json and hourly.json on the site.
#  3. share_image.py: the share image (og.png) and the Open Graph tags.
#  4. market_prices.py: on the first run after midnight, yesterday's last
#     live value is saved as that day's point in prices.json, committed and
#     pushed.
#
# Two ways to show the page (see the README):
#  - Your own web server: SITE is the folder the web server shows (where the
#    git repo is deployed). live.json, hourly.json and og.png are written
#    straight there, outside git.
#  - GitHub Pages or the like: SITE="$WEB" and HOURLY_PUSH=1. Then the three
#    files are committed and pushed every hour.

HERE="$(cd "$(dirname "$0")" && pwd)"   # the scripts folder, with api_key.txt and history/
WEB="$HERE/../web"                      # your own checkout of the site's git repo
SITE="$WEB"                             # the folder shown on the web
HOURLY_PUSH=1                           # 1 = push the live files every hour
SUBFOLDER=maplestory                    # the same as "subfolder" in settings.json
PY=python3                              # or "$HERE/venv/bin/python"

cd "$HERE" || exit 1
git -C "$WEB" pull -q --rebase --autostash
$PY fetch_history.py --rotate --web "$WEB"
$PY market_prices.py --live --web "$WEB" --live-out "$SITE/$SUBFOLDER/data/live.json" \
    || echo "$(date) ERROR: the live prices were not updated"
$PY share_image.py --site "$SITE"
$PY market_prices.py --web "$WEB" --live-out "$SITE/$SUBFOLDER/data/live.json" \
    || echo "$(date) ERROR: yesterday's point was not saved"

if [ "$HOURLY_PUSH" = 1 ] && [ "$SITE" = "$WEB" ]; then
    cd "$WEB" || exit 1
    git add "$SUBFOLDER/data/live.json" "$SUBFOLDER/data/hourly.json" "$SUBFOLDER/og.png" "$SUBFOLDER/index.html" 2>/dev/null
    if ! git diff --cached --quiet; then
        git commit -q -m "MapleStory live prices" && git push -q
    fi
fi
