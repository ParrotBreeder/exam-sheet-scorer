@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   答题卡小题分匹配系统  v3.0.0
echo   启动后将自动打开浏览器访问
echo ========================================
echo.
echo 正在启动服务，请稍候...
start "" "答题卡小题分匹配系统\答题卡小题分匹配系统.exe"
timeout /t 4 /nobreak >nul
start http://localhost:5000
echo.
echo 浏览器已打开，可访问 http://localhost:5000
echo 关闭此窗口不会影响服务运行。
