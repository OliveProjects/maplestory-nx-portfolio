#!/bin/bash
# MapleStory-priserna på servern, varje timme. I crontab (crontab -e):
#   5 * * * * /home/DITTNAMN/maplestory/scripts/run_hourly.sh >> /home/DITTNAMN/maplestory/logg.txt 2>&1
#
#  1. fetch_history.py --rotera: hämtar timhistoriken för de fem föremål
#     som hämtades längst sedan, och karaktärernas butiker en gång per dygn.
#     Den sjätte anropsplatsen i timmen lämnas åt synken på datorn.
#  2. market_prices.py --live: räknar om priserna ur det som hämtats och
#     skriver live.json och hourly.json i sajten.
#  3. share_image.py: delningsbilden (og.png) och Open Graph-taggarna.
#  4. market_prices.py: första körningen efter midnatt sparas gårdagens
#     sista livevärde som dagens punkt i prices.json, committas och pushas.
#
# Två sätt att visa sidan (se LASMIG.md):
#  - Egen webbserver: SAJT är mappen webbservern visar (där git-repot läggs
#    ut). live.json, hourly.json och og.png skrivs direkt där, utanför git.
#  - GitHub Pages eller liknande: SAJT="$WEB" och TIMPUSH=1. Då committas
#    och pushas de tre filerna varje timme.

MAPP="$(cd "$(dirname "$0")" && pwd)"   # skriptmappen, med api_key.txt och historik/
WEB="$MAPP/../web"                      # en egen utcheckning av sajtens git-repo
SAJT="$WEB"                             # mappen som visas på webben
TIMPUSH=1                               # 1 = pusha live-filerna varje timme
UNDERMAPP=maplestory                    # samma som "undermapp" i settings.json
PY=python3                              # eller "$MAPP/venv/bin/python"

cd "$MAPP" || exit 1
git -C "$WEB" pull -q --rebase --autostash
$PY fetch_history.py --rotera --web "$WEB"
$PY market_prices.py --live --web "$WEB" --live-ut "$SAJT/$UNDERMAPP/data/live.json" \
    || echo "$(date) FEL: livepriserna uppdaterades inte"
$PY share_image.py --sajt "$SAJT"
$PY market_prices.py --web "$WEB" --live-ut "$SAJT/$UNDERMAPP/data/live.json" \
    || echo "$(date) FEL: gårdagens punkt sparades inte"

if [ "$TIMPUSH" = 1 ] && [ "$SAJT" = "$WEB" ]; then
    cd "$WEB" || exit 1
    git add "$UNDERMAPP/data/live.json" "$UNDERMAPP/data/hourly.json" "$UNDERMAPP/og.png" "$UNDERMAPP/index.html" 2>/dev/null
    if ! git diff --cached --quiet; then
        git commit -q -m "MapleStory live prices" && git push -q
    fi
fi
