"""Takes a screenshot of the MapleStory window's client area and saves it as PNG.

Usage: python screenshot.py <out.png>
Prints whether the game is in front; if something else lies over the
window, the picture is of that, not of the game.
"""
import ctypes
import ctypes.wintypes as wt
import sys

from PIL import ImageGrab

u = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)


def find_window():
    k32 = ctypes.windll.kernel32
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not u.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = k32.OpenProcess(0x1000, False, pid.value)
        if h:
            buf = ctypes.create_unicode_buffer(260)
            n = wt.DWORD(260)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                if buf.value.lower().endswith("maplestory.exe"):
                    found.append(hwnd)
            k32.CloseHandle(h)
        return True

    u.EnumWindows(cb, 0)
    return found[0] if found else None


def main(out):
    hwnd = find_window()
    if not hwnd:
        print("MapleStory.exe has no visible window")
        return 1
    c = wt.RECT()
    u.GetClientRect(hwnd, ctypes.byref(c))
    p = wt.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(p))
    print("in front:", u.GetForegroundWindow() == hwnd,
          "| minimised:", bool(u.IsIconic(hwnd)),
          "| client area:", c.right, "x", c.bottom, "at", p.x, p.y)
    img = ImageGrab.grab(bbox=(p.x, p.y, p.x + c.right, p.y + c.bottom),
                         all_screens=True)
    img.save(out)
    print("saved:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
