"""Går igenom en öppen inventarieflik och sparar tooltipen för varje föremål.

Kräver att Item Inventory ligger öppet på Deco-fliken (var som helst i
fönstret; hitta_inventariet letar upp det). Körs som administratör, eftersom
spelet bara tar emot inmatning från ett program med samma behörighetsnivå.

UPPMÄTT I 3840x2160 (spelets klientyta i 4K, där spelet ritar inventariet
2,75 gånger förstorat). Rutnätets mått nedan (X0, DX, Y0, DY, CELL),
mall_flikar.png, DECO_FLIK och SKALA i bildmatch.py hör till just den
upplösningen. Med en annan upplösning stannar skriptet direkt i stället för
att peka runt på fel ställen; mät då om måtten eller skriv inventariet för
hand (synka.py --lista, se LASMIG.md).

  python inventera.py <utmapp>

Hovrar en hel sida, scrollar sex rader (ett hjulsteg = en rad) och hovrar
de rader som är nya. Varje hjulsteg kontrolleras för sig: ett steg som spelet
inte hann med får två nya försök innan det räknas som botten. Första versionen
tog ett enda uteblivet steg för botten och missade de sista raderna.

Skriver i utmappen:
  vy_NN.png          rutnätet när inventariets rad NN står överst
  tips_NN_r_c.png    tooltipen för rad r, kolumn c i den vyn
  logg.txt           vad som hände, rad för rad
Avbryter om spelet slutar ligga överst.
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

import numpy as np
from PIL import ImageGrab

from skarmbild import hitta_fonster

u = ctypes.windll.user32

# Rutnätet i klientytans pixlar, i klientytan UPPMATT.
UPPMATT = (3840, 2160)
X0, DX, KOLUMNER = 2486, 100, 5
Y0, DY, RADER = 600, 96, 6
CELL = 36            # halv sida på rutan som bedöms tom/inte tom
MAX_RADER = 200
UTAN_HOVRING = False


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


MOVE, ABSOLUTE, VIRTUALDESK, WHEEL = 0x0001, 0x8000, 0x4000, 0x0800


def _skicka(flags, dx=0, dy=0, data=0):
    inp = INPUT(type=0)
    inp.mi = MOUSEINPUT(dx, dy, ctypes.c_ulong(data & 0xFFFFFFFF).value,
                        flags, 0, 0)
    if u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise OSError("SendInput blockerades")


class Spel:
    def __init__(self, logg):
        self.logg = logg
        self.hwnd = hitta_fonster()
        if not self.hwnd:
            raise SystemExit("MapleStory.exe har inget synligt fönster")
        p = wt.POINT(0, 0)
        u.ClientToScreen(self.hwnd, ctypes.byref(p))
        self.ox, self.oy = p.x, p.y
        self.vl, self.vt = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        self.vw, self.vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)

    def kontroll(self):
        if u.GetForegroundWindow() != self.hwnd:
            self.logg("the game is no longer in front, stopping")
            raise SystemExit(2)

    def flytta(self, x, y):
        self.kontroll()
        sx, sy = self.ox + x, self.oy + y
        _skicka(MOVE | ABSOLUTE | VIRTUALDESK,
                round((sx - self.vl) * 65535 / (self.vw - 1)),
                round((sy - self.vt) * 65535 / (self.vh - 1)))

    def hjul(self, steg):
        self.kontroll()
        _skicka(WHEEL, data=120 * steg)

    def bild(self, x0, y0, x1, y1):
        x0, y0 = max(0, x0), max(0, y0)
        return ImageGrab.grab(bbox=(self.ox + x0, self.oy + y0,
                                    self.ox + x1, self.oy + y1),
                              all_screens=True)


def rutnat(spel):
    return spel.bild(X0 - 52, Y0 - 44, X0 + DX * (KOLUMNER - 1) + 52,
                     Y0 + DY * (RADER - 1) + 48)


def ar_tom(img, r, c):
    a = np.asarray(img.convert("L"), dtype=np.int16)
    cx, cy = 52 + DX * c, 44 + DY * r
    return a[cy - CELL:cy + CELL, cx - CELL:cx + CELL].std() < 6


SLOT = (225, 223, 213)          # inventarierutans färg i spelet
DECO_FLIK = (2900, 488, 2990, 532)   # Deco-flikens yta i klientytan
# Flikraden Equip..Cash (utan Deco, så att vald flik inte spelar roll),
# urklippt där den låg 2026-10-25. Rutnätets X0/Y0 och DECO_FLIK ovan hör
# till just det läget; hitta_inventariet flyttar dem dit inventariet ligger nu.
MALL_FLIKAR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mall_flikar.png")
MALL_LAGE = (2424, 486)


def hitta_inventariet(spel):
    """Letar upp Item Inventory var det än ligger i spelet och flyttar
    rutnätet dit. Ger en felbeskrivning, eller None. Första riktiga körningen
    (2026-10-26) stoppades för att inventariet låg på ett annat ställe än när
    rutnätet mättes upp; nu spelar läget ingen roll.
    Uppmätt: träff 1,00 där flikraden finns, 0,24 utan öppet inventarie."""
    global X0, Y0, DECO_FLIK
    import cv2
    c = wt.RECT()
    u.GetClientRect(spel.hwnd, ctypes.byref(c))
    hel = cv2.cvtColor(np.asarray(spel.bild(0, 0, c.right, c.bottom).convert("RGB")), cv2.COLOR_RGB2BGR)
    mall = cv2.imread(MALL_FLIKAR)
    res = cv2.matchTemplate(hel, mall, cv2.TM_CCOEFF_NORMED)
    _, traff, _, (x, y) = cv2.minMaxLoc(res)
    if traff < 0.8:
        return "cannot find Item Inventory in the game (match %.2f). Open it (key I)." % traff
    dx, dy = x - MALL_LAGE[0], y - MALL_LAGE[1]
    X0, Y0 = X0 + dx, Y0 + dy
    a, b, c_, d = DECO_FLIK
    DECO_FLIK = (a + dx, b + dy, c_ + dx, d + dy)
    return None


def ratt_flik(spel):
    """Ligger Item Inventory öppet på Deco-fliken, på det ställe rutnätet är
    uppmätt? Ger en felbeskrivning, eller None. Körs innan något scrollas
    eller hovras, så att skriptet aldrig börjar peka runt på fel ställe.

    Uppmätt 2026-10-26: en full sida har minst 51 av 120 rutor med rätt
    hörnfärg (ikonerna täcker resten), utan inventarie 0. Vald Deco-flik är
    till 71 % rosa, ovalda flikar till 0 %."""
    a = np.asarray(rutnat(spel).convert("RGB"), dtype=np.int16)
    traff = 0
    for r in range(RADER):
        for c in range(KOLUMNER):
            for dx, dy in ((-34, -34), (34, -34), (-34, 34), (34, 34)):
                p = a[44 + DY * r + dy, 52 + DX * c + dx]
                traff += all(abs(int(p[i]) - SLOT[i]) <= 14 for i in range(3))
    if traff < 30:
        return ("cannot find the inventory slots (%d of 120 corners). Open Item "
                "Inventory in the same place as before." % traff)
    f = np.asarray(spel.bild(*DECO_FLIK).convert("RGB"), dtype=np.int16)
    rosa = ((f[..., 0] - f[..., 1]) > 50).mean()
    if rosa < 0.4:
        return "the Deco tab is not selected (%.0f %% pink). Click Deco." % (rosa * 100)
    return None


def main(ut):
    os.makedirs(ut, exist_ok=True)
    loggfil = open(os.path.join(ut, "logg.txt"), "w", encoding="utf-8")

    def logg(s):
        loggfil.write(time.strftime("%H:%M:%S ") + s + "\n")
        loggfil.flush()

    spel = Spel(logg)
    start = wt.POINT()
    u.GetCursorPos(ctypes.byref(start))
    # UAC-rutan tar fokus; en minut att klicka i spelet igen.
    # 30 s räckte inte första gången.
    for _ in range(120):
        if u.GetForegroundWindow() == spel.hwnd:
            break
        time.sleep(0.5)
    spel.kontroll()
    logg("start, the game is in front")
    yta = wt.RECT()
    u.GetClientRect(spel.hwnd, ctypes.byref(yta))
    fel = None
    if (yta.right, yta.bottom) != UPPMATT:
        fel = ("the game's client area is %dx%d, but the grid is measured in %dx%d. "
               "Run the game in that resolution or use synka.py --lista (Synka lista.bat)."
               % (yta.right, yta.bottom, UPPMATT[0], UPPMATT[1]))
    if not fel:
        fel = hitta_inventariet(spel)
    if not fel:
        logg("inventory found, the grid starts at %d,%d" % (X0, Y0))
        fel = ratt_flik(spel)
    if fel:
        logg("ERROR: " + fel)
        loggfil.close()
        raise SystemExit(3)

    def stilla_vy():
        # Pekaren bort från rutorna innan bilden: spelet ritar sin egen
        # pekare och tooltip i rutnätet, och de hinner inte försvinna om
        # bilden tas direkt efter flytten.
        spel.flytta(X0 + 2 * DX, Y0 - 160)
        time.sleep(0.6)
        return rutnat(spel)

    def ett_steg_ned(fore):
        """Ett hjulsteg nedåt. Ger nya vyn, eller None om inget rörde sig
        efter tre försök (botten)."""
        for forsok in range(3):
            spel.flytta(X0 + 2 * DX, Y0 + 2 * DY)
            time.sleep(0.2)
            spel.hjul(-1)
            time.sleep(0.4 + 0.4 * forsok)
            efter = stilla_vy()
            skillnad = np.abs(np.asarray(fore.convert("L"), dtype=np.int16)
                              - np.asarray(efter.convert("L"), dtype=np.int16))
            if skillnad.mean() > 2:
                return efter
            logg("the wheel step did not move (attempt %d)" % (forsok + 1))
        return None

    try:
        spel.flytta(X0 + 2 * DX, Y0 + 2 * DY)
        time.sleep(0.3)
        spel.hjul(60)                       # längst upp
        time.sleep(0.8)
        vy = stilla_vy()
        overst = 0          # inventariets rad som står överst i vyn
        klar_t_o_m = -1     # sista inventarierad som hovrats
        while overst < MAX_RADER:
            vy.save(os.path.join(ut, "vy_%02d.png" % overst))
            for r in range(RADER):
                if overst + r <= klar_t_o_m or UTAN_HOVRING:
                    continue
                for c in range(KOLUMNER):
                    if ar_tom(vy, r, c):
                        continue
                    x, y = X0 + DX * c, Y0 + DY * r
                    spel.flytta(x, y)
                    time.sleep(0.45)
                    spel.bild(x - 900, y - 900, x + 1100, y + 900).save(
                        os.path.join(ut, "tips_%02d_%d_%d.png" % (overst, r, c)))
            klar_t_o_m = overst + RADER - 1
            logg("rows %d-%d read" % (overst, klar_t_o_m))
            vy = stilla_vy()
            botten = False
            for _ in range(RADER):
                ny = ett_steg_ned(vy)
                if ny is None:
                    botten = True
                    break
                vy, overst = ny, overst + 1
            if botten and overst + RADER - 1 <= klar_t_o_m:
                logg("bottom reached, %d rows" % (klar_t_o_m + 1))
                break
        logg("done")
    finally:
        u.SetCursorPos(start.x, start.y)
        loggfil.close()


if __name__ == "__main__":
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    # --utan-hovring: bara vyerna, inga tooltipar. synka.py känner igen
    # föremålen på bilden (bildmatch.py) och behöver inte hovra.
    UTAN_HOVRING = "--utan-hovring" in sys.argv
    main(sys.argv[1])
