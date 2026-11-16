@echo off
rem Synkar Deco-fliken till sidan (synka.py). Dubbelklicka.
rem Ingen admin behovs har: synka.py ber om admin sjalv nar inventeringen
rem startar, och da kommer UAC-rutan.
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  1. Open Item Inventory in the game and select the Deco tab.
echo  2. Accept the UAC prompt when it appears.
echo  3. Click in the game window within a minute and don't touch the mouse
echo     until it says you can let go.
echo.
python synka.py
echo.
pause
