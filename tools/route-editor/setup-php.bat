@echo off
setlocal EnableExtensions

set "DEST=%LOCALAPPDATA%\KaliopaRouteLab\php"
if exist "%DEST%\php.exe" (
    echo PHP already installed: %DEST%\php.exe
    exit /b 0
)

echo Downloading portable PHP 8.4 (NTS, Windows x64)...
if not exist "%DEST%" mkdir "%DEST%" >nul 2>&1
set "ZIP=%TEMP%\kaliopa-php-8.4.zip"

curl.exe -L --ssl-no-revoke --fail --max-time 600 -o "%ZIP%" "https://downloads.php.net/~windows/releases/latest/php-8.4-nts-Win32-vs17-x64-latest.zip"
if errorlevel 1 (
    echo Could not download PHP. Check the network or install PHP manually.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%DEST%' -Force"
if errorlevel 1 (
    echo Could not unpack PHP.
    pause
    exit /b 1
)
del /q "%ZIP%" >nul 2>&1

if not exist "%DEST%\php.exe" (
    echo PHP archive did not contain php.exe.
    pause
    exit /b 1
)
echo PHP installed: %DEST%\php.exe
exit /b 0
