@echo off
chcp 65001 >nul
title Giam sat Chuyen dong Wi-Fi CSI (ESP32-S3)
echo =========================================================
echo   Khoi dong Giao dien Giam sat Chuyen dong Wi-Fi CSI...
echo   Dia chi truy cap: http://localhost:8050
echo =========================================================
start "" "http://localhost:8050"
"E:\WifiSensingTools\venv\Scripts\python.exe" -u "%~dp0host\web_dashboard.py" --port COM4 --baud 115200 --calib "%~dp0models\motion_calib.json" --http-port 8050
