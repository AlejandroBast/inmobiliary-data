@echo off
setlocal
cd /d "%~dp0"
set "PATH=C:\Users\qalej\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;%PATH%"
where pnpm >nul 2>nul
if %errorlevel%==0 (
  pnpm run server
) else (
  "C:\Users\qalej\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" src\server.js
)
