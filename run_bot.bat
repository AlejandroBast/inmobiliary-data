@echo off
setlocal
cd /d "%~dp0"
where pnpm >nul 2>nul
if %errorlevel%==0 (
  pnpm run scan
) else (
  node src\cli.js scan --all
)
