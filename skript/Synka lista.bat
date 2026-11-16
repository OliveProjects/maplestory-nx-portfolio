@echo off
rem Synkar inventariet ur mina_foremal.txt i stallet for skarmen (synka.py --lista).
rem Skriv en rad per sort i filen: antalet och namnet, t.ex. "2 Angel Wand".
chcp 65001 >nul
cd /d "%~dp0"
python synka.py --lista mina_foremal.txt
echo.
pause
