"""Tar en skärmbild av MapleStory-fönstrets klientyta och sparar den som PNG.

Användning: python skarmbild.py <ut.png>
Skriver ut om spelet ligger överst; ligger något annat över fönstret blir
bilden av det, inte av spelet.
"""
import ctypes
import ctypes.wintypes as wt
import sys

from PIL import ImageGrab

u = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)


def hitta_fonster():
    psapi = ctypes.windll.psapi
    k32 = ctypes.windll.kernel32
    hittade = []

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
                    hittade.append(hwnd)
            k32.CloseHandle(h)
        return True

    u.EnumWindows(cb, 0)
    return hittade[0] if hittade else None


def main(ut):
    hwnd = hitta_fonster()
    if not hwnd:
        print("MapleStory.exe har inget synligt fönster")
        return 1
    c = wt.RECT()
    u.GetClientRect(hwnd, ctypes.byref(c))
    p = wt.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(p))
    print("överst:", u.GetForegroundWindow() == hwnd,
          "| minimerat:", bool(u.IsIconic(hwnd)),
          "| klientyta:", c.right, "x", c.bottom, "vid", p.x, p.y)
    img = ImageGrab.grab(bbox=(p.x, p.y, p.x + c.right, p.y + c.bottom),
                         all_screens=True)
    img.save(ut)
    print("sparad:", ut)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
