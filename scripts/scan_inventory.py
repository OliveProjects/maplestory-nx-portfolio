"""Goes through an open inventory tab and saves a view of the grid for every
scroll position (and, without --no-hover, each item's tooltip).

Needs Item Inventory open on the Deco tab (anywhere in the window;
find_inventory looks for it). Runs as administrator, since the game only
takes input from a program at the same privilege level.

MEASURED IN 3840x2160 (the game's client area in 4K, where it draws the
inventory 2.75 times enlarged). The grid sizes below (X0, DX, Y0, DY, CELL),
tab_template.png, DECO_TAB and SCALE in icon_match.py belong to that
resolution. In another resolution the script stops at once instead of
pointing at the wrong places; re-measure the sizes, read your own
screenshots (from_screenshots.py, any resolution) or write the
inventory by hand (sync.py --list, see the README).

  python scan_inventory.py <out folder> [--no-hover]

Hovers a whole page, scrolls six rows (one wheel step = one row) and hovers
the rows that are new. Every wheel step is checked on its own: a step the
game did not keep up with gets two more tries before it counts as the
bottom. The first version took a single missed step for the bottom and
lost the last rows.

Writes in the out folder:
  view_NN.png        the grid when the inventory's row NN is at the top
  tips_NN_r_c.png    the tooltip for row r, column c in that view
  log.txt            what happened, line by line
Stops if the game is no longer in front.
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

import numpy as np
from PIL import ImageGrab

from screenshot import find_window

u = ctypes.windll.user32

# The grid in client-area pixels, in a client area of MEASURED.
MEASURED = (3840, 2160)
X0, DX, COLUMNS = 2486, 100, 5
Y0, DY, ROWS = 600, 96, 6
CELL = 36            # half the side of the square judged empty or not
MAX_ROWS = 200
NO_HOVER = False


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


def _send(flags, dx=0, dy=0, data=0):
    inp = INPUT(type=0)
    inp.mi = MOUSEINPUT(dx, dy, ctypes.c_ulong(data & 0xFFFFFFFF).value,
                        flags, 0, 0)
    if u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise OSError("SendInput was blocked")


class Game:
    def __init__(self, log):
        self.log = log
        self.hwnd = find_window()
        if not self.hwnd:
            raise SystemExit("MapleStory.exe has no visible window")
        p = wt.POINT(0, 0)
        u.ClientToScreen(self.hwnd, ctypes.byref(p))
        self.ox, self.oy = p.x, p.y
        self.vl, self.vt = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        self.vw, self.vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)

    def check(self):
        if u.GetForegroundWindow() != self.hwnd:
            self.log("the game is no longer in front, stopping")
            raise SystemExit(2)

    def move(self, x, y):
        self.check()
        sx, sy = self.ox + x, self.oy + y
        _send(MOVE | ABSOLUTE | VIRTUALDESK,
              round((sx - self.vl) * 65535 / (self.vw - 1)),
              round((sy - self.vt) * 65535 / (self.vh - 1)))

    def wheel(self, steps):
        self.check()
        _send(WHEEL, data=120 * steps)

    def grab(self, x0, y0, x1, y1):
        x0, y0 = max(0, x0), max(0, y0)
        return ImageGrab.grab(bbox=(self.ox + x0, self.oy + y0,
                                    self.ox + x1, self.oy + y1),
                              all_screens=True)


def grid(game):
    return game.grab(X0 - 52, Y0 - 44, X0 + DX * (COLUMNS - 1) + 52,
                     Y0 + DY * (ROWS - 1) + 48)


def is_empty(img, r, c):
    a = np.asarray(img.convert("L"), dtype=np.int16)
    cx, cy = 52 + DX * c, 44 + DY * r
    return a[cy - CELL:cy + CELL, cx - CELL:cx + CELL].std() < 6


SLOT = (225, 223, 213)          # the inventory slot's colour in the game
DECO_TAB = (2900, 488, 2990, 532)   # the Deco tab's area in the client area
# The tab row Equip..Cash (without Deco, so that the selected tab doesn't
# matter), cut out where it was on 2026-10-25. The grid's X0/Y0 and DECO_TAB
# above belong to that position; find_inventory moves them to where the
# inventory is now.
TAB_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tab_template.png")
TAB_TEMPLATE_POS = (2424, 486)


def find_inventory(game):
    """Looks for Item Inventory wherever it is in the game and moves the
    grid there. Returns a description of what is wrong, or None. The first
    real run (2026-10-26) stopped because the inventory was somewhere else
    than when the grid was measured; now its position doesn't matter.
    Measured: match 1.00 where the tab row is, 0.24 without an open inventory."""
    global X0, Y0, DECO_TAB
    import cv2
    c = wt.RECT()
    u.GetClientRect(game.hwnd, ctypes.byref(c))
    whole = cv2.cvtColor(np.asarray(game.grab(0, 0, c.right, c.bottom).convert("RGB")), cv2.COLOR_RGB2BGR)
    template = cv2.imread(TAB_TEMPLATE)
    res = cv2.matchTemplate(whole, template, cv2.TM_CCOEFF_NORMED)
    _, match, _, (x, y) = cv2.minMaxLoc(res)
    if match < 0.8:
        return "cannot find Item Inventory in the game (match %.2f). Open it (key I)." % match
    dx, dy = x - TAB_TEMPLATE_POS[0], y - TAB_TEMPLATE_POS[1]
    X0, Y0 = X0 + dx, Y0 + dy
    a, b, c_, d = DECO_TAB
    DECO_TAB = (a + dx, b + dy, c_ + dx, d + dy)
    return None


def right_tab(game):
    """Is Item Inventory open on the Deco tab, where the grid is measured?
    Returns a description of what is wrong, or None. Runs before anything is
    scrolled or hovered, so the script never starts pointing at the wrong place.

    Measured 2026-10-26: a full page has at least 51 of 120 slot corners in
    the right colour (the icons cover the rest), without an inventory 0. The
    selected Deco tab is 71 % pink, unselected tabs 0 %."""
    a = np.asarray(grid(game).convert("RGB"), dtype=np.int16)
    hits = 0
    for r in range(ROWS):
        for c in range(COLUMNS):
            for dx, dy in ((-34, -34), (34, -34), (-34, 34), (34, 34)):
                p = a[44 + DY * r + dy, 52 + DX * c + dx]
                hits += all(abs(int(p[i]) - SLOT[i]) <= 14 for i in range(3))
    if hits < 30:
        return ("cannot find the inventory slots (%d of 120 corners). Open Item "
                "Inventory in the same place as before." % hits)
    f = np.asarray(game.grab(*DECO_TAB).convert("RGB"), dtype=np.int16)
    pink = ((f[..., 0] - f[..., 1]) > 50).mean()
    if pink < 0.4:
        return "the Deco tab is not selected (%.0f %% pink). Click Deco." % (pink * 100)
    return None


def main(out):
    os.makedirs(out, exist_ok=True)
    logfile = open(os.path.join(out, "log.txt"), "w", encoding="utf-8")

    def log(s):
        logfile.write(time.strftime("%H:%M:%S ") + s + "\n")
        logfile.flush()

    game = Game(log)
    start = wt.POINT()
    u.GetCursorPos(ctypes.byref(start))
    # The UAC prompt takes the focus; a minute to click in the game again.
    # 30 s was not enough the first time.
    for _ in range(120):
        if u.GetForegroundWindow() == game.hwnd:
            break
        time.sleep(0.5)
    game.check()
    log("start, the game is in front")
    area = wt.RECT()
    u.GetClientRect(game.hwnd, ctypes.byref(area))
    error = None
    if (area.right, area.bottom) != MEASURED:
        error = ("the game's client area is %dx%d, but the grid is measured in %dx%d. "
                 "Run the game in that resolution, or use your own screenshots or your list "
                 "(Sync.bat, options 2 and 3)." % (area.right, area.bottom, MEASURED[0], MEASURED[1]))
    if not error:
        error = find_inventory(game)
    if not error:
        log("inventory found, the grid starts at %d,%d" % (X0, Y0))
        error = right_tab(game)
    if error:
        log("ERROR: " + error)
        logfile.close()
        raise SystemExit(3)

    def still_view():
        # The pointer away from the slots before the picture: the game draws
        # its own pointer and tooltip in the grid, and they don't have time
        # to go away if the picture is taken right after the move.
        game.move(X0 + 2 * DX, Y0 - 160)
        time.sleep(0.6)
        return grid(game)

    def one_step_down(before):
        """One wheel step down. Returns the new view, or None if nothing
        moved after three tries (the bottom)."""
        for attempt in range(3):
            game.move(X0 + 2 * DX, Y0 + 2 * DY)
            time.sleep(0.2)
            game.wheel(-1)
            time.sleep(0.4 + 0.4 * attempt)
            after = still_view()
            diff = np.abs(np.asarray(before.convert("L"), dtype=np.int16)
                          - np.asarray(after.convert("L"), dtype=np.int16))
            if diff.mean() > 2:
                return after
            log("the wheel step did not move (attempt %d)" % (attempt + 1))
        return None

    try:
        game.move(X0 + 2 * DX, Y0 + 2 * DY)
        time.sleep(0.3)
        game.wheel(60)                       # to the top
        time.sleep(0.8)
        view = still_view()
        top = 0             # the inventory row at the top of the view
        done_to = -1        # the last inventory row hovered
        while top < MAX_ROWS:
            view.save(os.path.join(out, "view_%02d.png" % top))
            for r in range(ROWS):
                if top + r <= done_to or NO_HOVER:
                    continue
                for c in range(COLUMNS):
                    if is_empty(view, r, c):
                        continue
                    x, y = X0 + DX * c, Y0 + DY * r
                    game.move(x, y)
                    time.sleep(0.45)
                    game.grab(x - 900, y - 900, x + 1100, y + 900).save(
                        os.path.join(out, "tips_%02d_%d_%d.png" % (top, r, c)))
            done_to = top + ROWS - 1
            log("rows %d-%d read" % (top, done_to))
            view = still_view()
            bottom = False
            for _ in range(ROWS):
                new = one_step_down(view)
                if new is None:
                    bottom = True
                    break
                view, top = new, top + 1
            if bottom and top + ROWS - 1 <= done_to:
                log("bottom reached, %d rows" % (done_to + 1))
                break
        log("done")
    finally:
        u.SetCursorPos(start.x, start.y)
        logfile.close()


if __name__ == "__main__":
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    # --no-hover: only the views, no tooltips. sync.py recognises the items
    # from the picture (icon_match.py) and doesn't need to hover.
    NO_HOVER = "--no-hover" in sys.argv or "--utan-hovring" in sys.argv
    main(sys.argv[1])
