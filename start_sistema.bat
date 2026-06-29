@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Get-NetTCPConnection -LocalPort 3306 -State Listen -ErrorAction SilentlyContinue)) { exit 1 }"
if not %errorlevel%==0 (
  call "%~dp0start_mysql.bat"
  timeout /t 8 /nobreak >nul
)
call "%~dp0start_front.bat"
