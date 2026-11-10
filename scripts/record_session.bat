@echo off
chcp 65001 >nul
title Thu Du Lieu Thuc Nghiem Trong Nha - Wi-Fi CSI (ESP32-S3)
"E:\WifiSensingTools\venv\Scripts\python.exe" -u "%~dp0..\host\record.py" --port COM4 --baud 921600 %*
set "record_exit=%errorlevel%"
pause
exit /b %record_exit%
