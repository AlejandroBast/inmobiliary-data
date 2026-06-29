@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Get-NetTCPConnection -LocalPort 3306 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -FilePath 'C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\mysql-8.4.9-winx64\bin\mysqld.exe' -ArgumentList '--defaults-file=\"C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\my.ini\"' -WindowStyle Hidden; Start-Sleep -Seconds 8 }"
call "%~dp0start_front.bat"
