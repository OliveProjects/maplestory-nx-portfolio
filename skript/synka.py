"""Synkar Deco-fliken till sidan.

  python synka.py                   inventera, visa skillnaden, fråga, publicera
  python synka.py --ja              publicera utan att fråga
  python synka.py --fran <mapp>     använd en befintlig inventering (vy_*.png)
  python synka.py --lista <fil>     inventariet ur en textfil i stället för
                                    skärmen (vilken upplösning som helst)

Listfilen har en rad per sort: antalet och sedan namnet som spelet skriver
det, eller id:t. Har två föremål samma namn säger skriptet till och visar
id:na; skriv då id:t i stället. Tomma rader och rader som börjar med # hoppas
över.

    2 Angel Wand
    1 White Label Ring
    1 1112100

Före en automatisk körning: öppna Item Inventory på Deco-fliken och låt
spelet ligga överst. Godkänn UAC-rutan (spelet tar bara emot musen från ett
program som körs som administratör), klicka sedan i spelet om det tappat
fokus, och rör inte musen förrän det är klart.

Steg:
  1. inventera.py --utan-hovring (som admin): letar upp inventariet,
     kontrollerar att Deco-fliken är vald, scrollar igenom och sparar vyerna
  2. gruppera.py: grupperar rutorna efter ikon och räknar
  3. bildmatch.py: varje grupp känns igen mot spelets egna ikoner
     (ikonbibliotek.npz, byggt ur WZ-filerna med ikonbibliotek.py)
  4. skillnaden mot förra inventeringen visas; inget publiceras utan ja
  5. deco.json, ikoner, inventory.json och aktivitetsloggen skrivs, dagens
     värdepunkt får de nya antalen, och allt committas och pushas

Första gången (ingen deco.json än) blir allt startinnehav: inga rader i
aktivitetsloggen, och skriptet frågar vad föremålen kostade i snitt.

En grupp som inte känns igen säkert stoppar publiceringen.
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

import gemensamt  # noqa: E402
import installningar as inst  # noqa: E402
from gemensamt import DECO, MANADER, SIDA, WEB, skriv_json  # noqa: E402
from hamta_historik import TILL_MARKNAD  # noqa: E402
from marknadspriser import api  # noqa: E402

ACTIVITY = os.path.join(SIDA, "data", "activity.json")
# Kvot mellan näst bästa och bästa föremålets fel. Rätt föremål låg på
# minst 1,09 i testet (114 rutor, 45 sorter, alla rätt).
SAKER_KVOT = 1.04


def steg(nr, text):
    """Rubrik för varje steg, så att det syns vad som händer (efter
    skanningen var det annars tyst medan föremålen kändes igen)."""
    print("\n" + "─" * 60)
    print("STEP %d OF 4 · %s" % (nr, text))
    print("─" * 60)


def pagar(text):
    """En rad som skrivs över, bara i fönstret (inte i senaste_synk.txt)."""
    sys.__stdout__.write("\r  " + text.ljust(58))
    sys.__stdout__.flush()


def sluta(text):
    """Avbryt med ett meddelande som också hamnar i senaste_synk.txt
    (SystemExit med text går till stderr och hade saknats där)."""
    print(text)
    sys.exit(1)


def inventera(ut):
    steg(1, "Reading the game")
    print("  Before this step: open Item Inventory in the game and select the")
    print("  Deco tab, where it usually sits on screen.")
    print("  Accept the UAC prompt, then click in the game within a minute.")
    print("  Don't touch the mouse until it says you can let go.")
    kommando = ("Start-Process -FilePath '%s' -ArgumentList '\"%s\"','\"%s\"','--utan-hovring' "
                "-WorkingDirectory '%s' -Verb RunAs -Wait -WindowStyle Minimized"
                % (sys.executable, os.path.join(HERE, "inventera.py"), ut, HERE))
    subprocess.run(["powershell", "-NoProfile", "-Command", kommando], check=True)
    logg = os.path.join(ut, "logg.txt")
    text = open(logg, encoding="utf-8").read() if os.path.exists(logg) else ""
    rader = text.strip().splitlines()
    if not rader or not rader[-1].endswith((" done", " klar")):  # sista raden: skanningen blev klar
        sluta("The scan did not finish:\n" + (text or "(no log)"))
    print("  Done with the game. You can let go of the mouse and use the computer.")


def kanna_igen(mapp):
    """{id: (namn, kategori, antal)} i inventariets ordning, och en lista
    med grupper som inte gick att känna igen säkert."""
    steg(2, "Recognising the items")
    print("  Each slot is compared with the game's own icons. This runs on the")
    print("  computer; the game is no longer needed.")
    start = time.time()
    if not any(f.startswith("vy_") for f in os.listdir(mapp)):
        sluta("  No screenshots in %s: the scan never finished." % mapp)
    if not os.path.exists(os.path.join(HERE, "ikonbibliotek.npz")):
        sluta("ikonbibliotek.npz is missing: run python ikonbibliotek.py first.")
    pagar("Loading the game's icons ...")
    from bildmatch import Bibliotek, kanna_igen_grupp, rutor
    from gruppera import grupper
    bib = Bibliotek()
    pagar("Grouping the slots by icon ...")
    fonster = {(g, c): f for g, c, f in rutor(mapp)}
    hittat, osakra = {}, []
    alla = list(grupper(mapp))
    for nr, grp in enumerate(alla, 1):
        pagar("Recognising kind %d of %d ..." % (nr, len(alla)))
        i, fel, kvot = kanna_igen_grupp(bib, [fonster[rc] for rc in grp["rutor"]])
        iid, namn, kat = str(bib.ids[i]), str(bib.namn[i]), str(bib.kats[i])
        if kvot < SAKER_KVOT:
            osakra.append("%d from row %d: probably %s (%s), ratio %.2f"
                          % (len(grp["rutor"]), grp["rutor"][0][0], namn, iid, kvot))
            continue
        n0, k0, a0 = hittat.get(iid, (namn, kat, 0))
        hittat[iid] = (n0, k0, a0 + len(grp["rutor"]))
    pagar("")
    sys.__stdout__.write("\r")
    print("  Done in %d seconds." % round(time.time() - start))
    return hittat, osakra


def ur_lista(fil):
    """Som kanna_igen, men ur en textfil med "antal namn" eller "antal id"
    per rad. Namnen slås upp i spelets egna filer."""
    from ikoner import katalog
    per_namn, per_id = katalog()
    hittat, oklara = {}, []
    for nr, rad in enumerate(open(fil, encoding="utf-8-sig"), 1):
        rad = rad.strip()
        if not rad or rad.startswith("#"):
            continue
        antal, _, vad = rad.partition(" ")
        vad = vad.strip()
        if not antal.isdigit() or not vad:
            oklara.append("rad %d: \"%s\" (skriv antalet först, t.ex. 2 Angel Wand)" % (nr, rad))
            continue
        if vad.isdigit():
            if vad not in per_id:
                oklara.append("rad %d: inget föremål har id %s" % (nr, vad))
                continue
            iid, (namn, kat) = vad, per_id[vad]
        else:
            kandidater = per_namn.get(vad) or next(
                (v for k, v in per_namn.items() if k.lower() == vad.lower()), [])
            if not kandidater:
                oklara.append("rad %d: hittar inget föremål som heter \"%s\"" % (nr, vad))
                continue
            if len(kandidater) > 1:
                # Ikonerna sparas, så att det går att se vilket som är vilket.
                from ikoner import ikon
                mapp = os.path.join(HERE, "kandidater")
                os.makedirs(mapp, exist_ok=True)
                for k, i in kandidater:
                    bild = ikon(k, i)
                    if bild is not None:
                        bild.resize((bild.width * 3, bild.height * 3), 0).save(os.path.join(mapp, i + ".png"))
                oklara.append("rad %d: flera föremål heter \"%s\", skriv id:t i stället: %s "
                              "(ikonerna ligger i mappen kandidater)"
                              % (nr, vad, ", ".join(i for _, i in kandidater)))
                continue
            kat, iid = kandidater[0]
            namn = per_id[iid][0]
        n0, k0, a0 = hittat.get(iid, (namn, kat, 0))
        hittat[iid] = (n0, k0, a0 + int(antal))
    return hittat, oklara


def butiksforsaljningar():
    """{marknadens id: snittpris per styck} för det karaktärernas butiker har
    sålt, enligt maplestory.market. Tomt om anropet inte går (t.ex.
    timgränsen nådd); då frågar synken som förut."""
    try:
        salt = {}
        for k in inst.KARAKTARER:
            try:
                svar = api("owners/" + k)
            except urllib.error.HTTPError as e:
                if e.code == 404:  # aldrig setts med butik
                    continue
                raise
            for s in svar.get("sold_items", []):
                if s["units"]:
                    salt[str(s["item_id"])] = round(s["mesos"] / s["units"])
        return salt
    except Exception as e:  # noqa: BLE001
        print("(could not read the shops' sales: %s)" % e)
        return {}


class Dubbel:
    """Skriver allt till både fönstret och senaste_synk.txt, så att
    körningen går att läsa i efterhand."""
    def __init__(self, *strommar):
        self.strommar = strommar

    def write(self, s):
        for st in self.strommar:
            st.write(s)
            st.flush()

    def flush(self):
        for st in self.strommar:
            st.flush()


def publicera(meddelande):
    git = ["git", "-C", WEB]
    print("\n  Uploading to the site ...")
    subprocess.run(git + ["add", inst.UNDERMAPP], check=True)
    subprocess.run(git + ["commit", "-m", meddelande], check=True)
    for r in inst.REMOTES:
        subprocess.run(git + ["push", r, "main"], check=True)
    print("\nDONE. Published: " + inst.SAJT_URL)


def forsta_gangen(hittat, args):
    """Första inventeringen: startinnehavet. Ingen aktivitet, en första
    prispost utan priser (servern bygger priserna, se LASMIG.md) och
    startinnehavet i activity.json, med vad det kostade om du vet det."""
    if "--ja" not in args and input("\nPublish as the starting holdings? [y/N] ").strip().lower() not in ("j", "ja", "y", "yes"):
        sluta("Nothing published.")
    snitt = None
    if "--ja" not in args:
        svar = input("What did the items cost on average each, in mesos? (e.g. 8k, Enter = don't know) ")
        snitt = gemensamt.tolka(svar) if svar.strip() else None
    idag = datetime.date.today().isoformat()
    skriv_json(DECO, {"datum": idag, "foremal": [{"namn": n, "antal": a, "kategori": k, "id": i}
                                                 for i, (n, k, a) in hittat.items()]})
    import ikoner
    ikoner.main(os.path.join(SIDA, "icons"))
    items = gemensamt.skriv_inventory()
    antal = {it["id"]: it["qty"] for it in items}
    skriv_json(gemensamt.PRICES, {"updates": [{"date": idag, "prices": {}, "qty": antal}]})
    oppning = {"date": idag, "month": idag[:7], "items": sum(antal.values()), "kinds": len(antal)}
    if snitt:
        # Uppskattat: samma pris för alla. Exakta priser per sort kan skrivas
        # in i buy_prices ({id: pris}) i efterhand; spent räknas inte om då.
        oppning.update({"spent": snitt * oppning["items"], "spent_estimated": True,
                        "buy_prices": {}, "default_buy_price": snitt})
    skriv_json(ACTIVITY, {"opening": oppning, "events": []})
    d = datetime.date.today()
    publicera("MapleStory: first inventory %d %s" % (d.day, MANADER[d.month - 1]))


def main(args):
    sys.stdout.reconfigure(encoding="utf-8")
    logg = open(os.path.join(HERE, "senaste_synk.txt"), "w", encoding="utf-8")
    sys.stdout = Dubbel(sys.stdout, logg)
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stderr = Dubbel(sys.stderr, logg)
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    if "--lista" in args:
        hittat, osakra = ur_lista(args[args.index("--lista") + 1])
        mapp = None
    else:
        if "--fran" in args:
            mapp = args[args.index("--fran") + 1]
        else:
            # Bredvid skriptet, inte i Temp: där går den att granska efteråt.
            # Skrivs över vid nästa körning.
            mapp = os.path.join(HERE, "senaste_inventering")
            shutil.rmtree(mapp, ignore_errors=True)
            os.makedirs(mapp)
            inventera(mapp)
        hittat, osakra = kanna_igen(mapp)
    steg(3, "Comparing with the last sync")
    print("  %d items in %d kinds." % (sum(a for _, _, a in hittat.values()), len(hittat)))
    if osakra:
        print("\nCould not be recognised with certainty:")
        for o in osakra:
            print("  " + o)
        sluta("Nothing published." + (" The scan is kept in %s." % mapp if mapp else ""))
    if not hittat:
        sluta("No items found. Nothing published.")

    # Servern committar dagspunkten själv; hämta den först, annars avvisas
    # pushen och prices.json skrivs på en gammal version.
    subprocess.run(["git", "-C", WEB, "pull", "--rebase", "--autostash", "-q", inst.REMOTES[0], "main"],
                   check=False)
    if not os.path.exists(DECO):
        for _, (namn, _, a) in hittat.items():
            print("  %3d  %s" % (a, namn))
        forsta_gangen(hittat, args)
        return

    gammal = json.load(open(DECO, encoding="utf-8"))
    forra = {f["id"]: f for f in gammal["foremal"]}
    andringar = []
    for iid in list(forra) + [i for i in hittat if i not in forra]:
        d = hittat.get(iid, (0, 0, 0))[2] - forra.get(iid, {}).get("antal", 0)
        if d:
            namn = hittat[iid][0] if iid in hittat else forra[iid]["namn"]
            andringar.append((iid, namn, d))
    if not andringar:
        print("No changes since %s." % gammal["datum"])
        return
    print("\nChanges since %s:" % gammal["datum"])
    for _, namn, d in andringar:
        print("  %+3d  %s" % (d, namn))
    if "--ja" not in args and input("\nPublish? [y/N] ").strip().lower() not in ("j", "ja", "y", "yes"):
        sluta("Nothing published.")

    steg(4, "Updating your site")
    print("  Icons, the inventory and the activity log ...")
    idag = datetime.date.today().isoformat()
    skriv_json(DECO, {"datum": idag, "foremal": [{"namn": n, "antal": a, "kategori": k, "id": i}
                                                 for i, (n, k, a) in hittat.items()]})
    import ikoner
    ikoner.main(os.path.join(SIDA, "icons"))
    items = gemensamt.skriv_inventory()

    # Aktivitetsloggen: en rad per ändring, med senast kända pris.
    data = json.load(open(gemensamt.PRICES, encoding="utf-8"))
    senaste = {}
    for u in data["updates"]:
        senaste.update(u["prices"])
    logg = json.load(open(ACTIVITY, encoding="utf-8")) if os.path.exists(ACTIVITY) else {"events": []}
    salt = butiksforsaljningar() if any(d < 0 for _, _, d in andringar) and "--ja" not in args else {}
    for iid, namn, d in andringar:
        rad = {"date": idag, "id": iid, "name": namn, "delta": d, "price": senaste.get(iid)}
        # Sålt? Sidan visar då SOLD och "sold for …" i stället för REMOVED och
        # dagens marknadspris. Har marknaden sett det säljas i en butik
        # föreslås det priset (Enter tar det, n = inte sålt). Inte sålt:
        # bortgivet ("given": true) eller använt ("used": true), båda uttag.
        if d < 0 and "--ja" not in args:
            forslag = salt.get(TILL_MARKNAD.get(iid, iid))
            if forslag:
                svar = input("Did you sell %s? The shop sold it for %s each. Enter = yes, another price, n = no: "
                             % (namn, format(forslag, ",").replace(",", " ")))
                pris = forslag if not svar.strip() else None if svar.strip().lower() == "n" else gemensamt.tolka(svar)
            else:
                svar = input("Did you sell %s? Price each (e.g. 20k), Enter = no: " % namn)
                pris = gemensamt.tolka(svar) if svar.strip() else None
            if pris:
                rad["sold_price"] = pris
            else:
                svar = input("  Did you give %s away (g) or use it (u)? Enter = neither: " % namn).strip().lower()
                if svar in ("g", "given", "gave"):
                    rad["given"] = True
                elif svar in ("u", "used", "use"):
                    rad["used"] = True
        # Köpt för meso? Då räknas det in i snittkostnaden och skillnaden mot
        # marknadspriset som handel i månadsrutnätet. Köpt för NX eller fått:
        # Enter, och raden är neutral.
        if d > 0 and "--ja" not in args:
            svar = input("Did you buy %s for mesos? Price each, Enter = no: " % namn)
            pris = gemensamt.tolka(svar) if svar.strip() else None
            if pris:
                rad["buy_price"] = pris
        logg["events"].append(rad)
    skriv_json(ACTIVITY, logg)

    # Dagens värdepunkt får de nya antalen. Finns ingen prispost i dag kopieras
    # förra dagens priser, markerade så att sidan inte läser dem som en ny
    # prisrörelse per föremål.
    antal = {it["id"]: it["qty"] for it in items}
    if data["updates"] and data["updates"][-1]["date"] == idag:
        data["updates"][-1]["qty"] = antal
    else:
        forra_pris = data["updates"][-1]["prices"] if data["updates"] else {}
        data["updates"].append({"date": idag, "prices": {i: p for i, p in forra_pris.items() if i in antal},
                                "qty": antal, "inventory": True})
    skriv_json(gemensamt.PRICES, data)

    d = datetime.date.today()
    kort = ", ".join("%+d %s" % (dd, n) for _, n, dd in andringar[:4]) + (" …" if len(andringar) > 4 else "")
    publicera("MapleStory inventory synced %d %s: %s" % (d.day, MANADER[d.month - 1], kort))


if __name__ == "__main__":
    main(sys.argv[1:])
