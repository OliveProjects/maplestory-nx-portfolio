@echo off
rem Double-click: a menu (menu.py). 1 scans the Deco tab, 2 syncs from your
rem list, 3 sets the mesos:NX rate, 4 updates your site, 5 enters prices by
rem hand. No admin needed here: sync.py asks for admin itself when the scan
rem starts (the UAC prompt).
chcp 65001 >nul
cd /d "%~dp0"
python menu.py
echo.
pause
