@echo off
setlocal
cd /d "%~dp0"
where pnpm >nul 2>nul
if %errorlevel%==0 (
  pnpm install
  pnpm approve-builds sharp
  pnpm rebuild sharp
  pnpm run playwright:install
) else (
  npm install
  npx playwright install chromium
)
