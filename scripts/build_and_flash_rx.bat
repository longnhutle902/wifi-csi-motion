@echo off
setlocal
if "%~1"=="" (
    echo Cach dung: scripts\build_and_flash_rx.bat COMx
    exit /b 1
)
set T=E:\WifiSensingTools
set IDF_TOOLS_PATH=%T%\espressif
set IDF_PATH=%T%\esp-idf
set IDF_PYTHON_ENV_PATH=%T%\espressif\python_env\idf5.3_py3.11_env
set PATH=%T%\Python311;%T%\Python311\Scripts;%T%\Git\cmd;%PATH%
call "%T%\esp-idf\export.bat"
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0..\firmware\csi_rx"
if errorlevel 1 exit /b %errorlevel%
call idf.py -p "%~1" build flash
if errorlevel 1 exit /b %errorlevel%
echo RX firmware flashed on %~1. Run start_dashboard.bat to open the dashboard.
