@echo off
setlocal EnableExtensions

set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8099" ^| findstr "LISTENING"') do (
    set "FOUND=1"
    taskkill /PID %%P /F >nul 2>&1
)

if defined FOUND (
    echo Route Lab stopped on port 8099.
) else (
    echo Route Lab is not running on port 8099.
)
pause
exit /b 0
