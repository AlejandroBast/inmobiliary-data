@echo off
setlocal
cd /d "%~dp0"
set "DB_SQL=%~dp0inmobiliary_db.sql"

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

if defined MYSQL_HOME if exist "%MYSQL_HOME%\bin\mysql.exe" set "MYSQL_EXE=%MYSQL_HOME%\bin\mysql.exe"
if not defined MYSQL_EXE if exist "%~dp0mysql\bin\mysql.exe" set "MYSQL_EXE=%~dp0mysql\bin\mysql.exe"
if not defined MYSQL_EXE set "MYSQL_EXE=mysql"

if defined DB_PASSWORD set "MYSQL_PWD=%DB_PASSWORD%"
"%MYSQL_EXE%" --host=%DB_HOST% --port=%DB_PORT% --user=%DB_USER% < "%DB_SQL%"
if %errorlevel%==0 (
  echo Base de datos importada correctamente.
) else (
  echo Error importando la base de datos.
  echo Revisa que MySQL este instalado, iniciado y disponible en PATH o MYSQL_HOME.
)
