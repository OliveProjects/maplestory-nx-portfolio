@echo off
rem Double-click: a menu (menu.py). 1 scans the Deco tab, 2 reads your own
rem screenshots, 3 syncs from your list, 4 sets the mesos:NX rate, 5 updates
rem your site, 6 enters prices by hand. No admin needed here: sync.py asks
rem for admin itself when the scan starts (the UAC prompt).
chcp 65001 >nul
cd /d "%~dp0"
python menu.py
echo.
pause
