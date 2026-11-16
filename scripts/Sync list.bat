@echo off
rem Syncs the inventory from my_items.txt instead of the screen (sync.py --lista).
rem Write one line per kind in the file: the count and the name, e.g. "2 Angel Wand".
chcp 65001 >nul
cd /d "%~dp0"
python sync.py --lista my_items.txt
echo.
pause
