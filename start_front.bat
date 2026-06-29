@echo off
setlocal
cd /d "%~dp0"
where pnpm >nul 2>nul
if %errorlevel%==0 (
  pnpm run server
) else (
  node src\server.js
)
