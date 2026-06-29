@echo off
setlocal
cd /d "%~dp0"
set "PATH=C:\Users\qalej\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;%PATH%"
"C:\Users\qalej\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd" install
"C:\Users\qalej\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd" approve-builds sharp
"C:\Users\qalej\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd" rebuild sharp
"C:\Users\qalej\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd" run playwright:install
