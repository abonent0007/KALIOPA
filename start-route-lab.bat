@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "PHP_EXE="

rem 1) PHP from PATH
where php >nul 2>nul
if not errorlevel 1 (
    set "PHP_EXE=php"
    goto run
)

rem 2) persistent portable PHP used by this fork
set "PHP_HOME=%LOCALAPPDATA%\KaliopaRouteLab\php"
if exist "%PHP_HOME%\php.exe" (
    set "PHP_EXE=%PHP_HOME%\php.exe"
    goto run
)

rem 3) temporary portable PHP from earlier runs
if exist "%TEMP%\php84\php.exe" (
    set "PHP_EXE=%TEMP%\php84\php.exe"
    goto run
)

rem 4) download the official Windows PHP build once
call "%ROOT%tools\route-editor\setup-php.bat"
if exist "%PHP_HOME%\php.exe" (
    set "PHP_EXE=%PHP_HOME%\php.exe"
    goto run
)

echo.
echo PHP not found. Install PHP 8+ or run:
echo   tools\route-editor\setup-php.bat
echo.
pause
exit /b 1

:run
echo.
echo KALIOPA Route Lab: http://127.0.0.1:8099/
echo Press Ctrl+C to stop.
echo.
"%PHP_EXE%" -S 127.0.0.1:8099 -t "%ROOT%tools\route-editor"
echo.
echo Route Lab stopped.
pause
exit /b 0
