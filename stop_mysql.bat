@echo off
setlocal
cd /d "%~dp0"

for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
  if /i "%%A"=="DB_HOST" set "DB_HOST=%%B"
  if /i "%%A"=="DB_PORT" set "DB_PORT=%%B"
  if /i "%%A"=="DB_USER" set "DB_USER=%%B"
  if /i "%%A"=="DB_PASSWORD" set "DB_PASSWORD=%%B"
  if /i "%%A"=="MYSQL_HOME" set "MYSQL_HOME=%%B"
)

if not defined DB_HOST set "DB_HOST=127.0.0.1"
if not defined DB_PORT set "DB_PORT=3306"
if not defined DB_USER set "DB_USER=root"

if defined MYSQL_HOME if exist "%MYSQL_HOME%\bin\mysqladmin.exe" set "MYSQLADMIN_EXE=%MYSQL_HOME%\bin\mysqladmin.exe"
if not defined MYSQLADMIN_EXE if exist "%~dp0mysql\bin\mysqladmin.exe" set "MYSQLADMIN_EXE=%~dp0mysql\bin\mysqladmin.exe"
if not defined MYSQLADMIN_EXE (
  where mysqladmin >nul 2>nul
  if not errorlevel 1 set "MYSQLADMIN_EXE=mysqladmin"
)

if not defined MYSQLADMIN_EXE (
  echo No se encontro mysqladmin.exe.
  echo Instala MySQL, agrega MySQL al PATH o define MYSQL_HOME con la carpeta de MySQL.
  exit /b 1
)

if defined DB_PASSWORD set "MYSQL_PWD=%DB_PASSWORD%"
"%MYSQLADMIN_EXE%" --host=%DB_HOST% --port=%DB_PORT% --user=%DB_USER% shutdown
