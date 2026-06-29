@echo off
setlocal
cd /d "%~dp0"

for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
  if /i "%%A"=="MYSQL_HOME" set "MYSQL_HOME=%%B"
)

if defined MYSQL_HOME if exist "%MYSQL_HOME%\bin\mysqld.exe" set "MYSQLD_EXE=%MYSQL_HOME%\bin\mysqld.exe"
if not defined MYSQLD_EXE if exist "%~dp0mysql\bin\mysqld.exe" set "MYSQLD_EXE=%~dp0mysql\bin\mysqld.exe"
if not defined MYSQLD_EXE (
  where mysqld >nul 2>nul
  if not errorlevel 1 set "MYSQLD_EXE=mysqld"
)

if not defined MYSQLD_EXE (
  echo No se encontro mysqld.exe.
  echo Instala MySQL, agrega MySQL al PATH o define MYSQL_HOME con la carpeta de MySQL.
  exit /b 1
)

if exist "%~dp0my.ini" (
  start "Inmobiliary MySQL" /min "%MYSQLD_EXE%" --defaults-file="%~dp0my.ini"
) else (
  start "Inmobiliary MySQL" /min "%MYSQLD_EXE%"
)
echo MySQL iniciado en 127.0.0.1:3306
