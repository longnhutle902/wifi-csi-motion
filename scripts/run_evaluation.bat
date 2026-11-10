@echo off
"E:\WifiSensingTools\venv\Scripts\python.exe" "%~dp0..\host\evaluate.py" --data "%~dp0..\data\sessions" --out "%~dp0..\reports"
set "evaluation_exit=%errorlevel%"
pause
exit /b %evaluation_exit%
