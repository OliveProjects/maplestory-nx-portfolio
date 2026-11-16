@echo off
rem Dubbelklicka: en meny (meny.py). 1 skannar Deco-fliken, 2 synkar fran
rem listan, 3 anger kursen mesos:NX, 4 uppdaterar sidan. Ingen admin behovs
rem har: synka.py ber om admin sjalv nar skanningen startar (UAC-rutan).
chcp 65001 >nul
cd /d "%~dp0"
python meny.py
echo.
pause
