@echo off
echo ========================================
echo   Answer Sheet Scoring System
echo ========================================
echo.
echo Starting service...
echo.
start "" http://localhost:5000
C:\Users\gao\anaconda3\envs\exam_scoring\python.exe app.py
pause
