@echo off
title ModelScope App Launcher

:: [CRITICAL FIX] Switch to the script's directory to find main.py
cd /d "%~dp0"

echo ==========================================
echo      Checking Environment...
echo ==========================================

:: Install dependencies using Tsinghua mirror for speed
echo [INFO] Installing dependencies from requirements.txt...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo ==========================================
echo      Starting the App...
echo ==========================================

:: Run the Flet app
python main.py

:: If the app crashes, show an error message
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The application crashed!
    echo Please take a screenshot of the error message above.
)

:: Pause the window so you can see what happened
pause