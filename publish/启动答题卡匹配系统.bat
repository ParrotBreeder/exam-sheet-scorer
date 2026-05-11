@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   答题卡小题分匹配系统  v3.0.3
echo ========================================
echo.
echo 正在启动服务...
start "" "答题卡小题分匹配系统\答题卡小题分匹配系统.exe"

echo 等待 Flask 监听端口 5000（最多 30 秒）...
set /a _try=0
:waitloop
set /a _try+=1
timeout /t 1 /nobreak >nul
curl --max-time 1 -s -o nul http://localhost:5000/api/dependencies && goto ready
if %_try% GEQ 30 goto fail
goto waitloop

:ready
echo 服务已就绪，正在打开浏览器...
start http://localhost:5000
echo.
echo ========================================
echo 浏览器已打开。如需停止服务，请关闭
echo 名为"答题卡小题分匹配系统.exe"的控制台窗口。
echo ========================================
exit /b 0

:fail
echo.
echo [错误] 服务在 30 秒内未启动。
echo 请检查 答题卡小题分匹配系统.exe 的控制台窗口里的错误信息。
echo 常见原因：端口 5000 被其它进程占用。
echo.
pause
exit /b 1
