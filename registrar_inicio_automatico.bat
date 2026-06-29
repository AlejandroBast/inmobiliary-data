@echo off
setlocal
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_FILE=%STARTUP_DIR%\InmobiliaryDataBot.bat"
copy /Y "%~dp0startup_InmobiliaryDataBot.bat" "%STARTUP_FILE%" >nul
if %errorlevel%==0 (
  echo Inicio automatico registrado en:
  echo %STARTUP_FILE%
) else (
  echo No se pudo registrar el inicio automatico.
)
