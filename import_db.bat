@echo off
setlocal
set "MYSQL_HOME=C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\mysql-8.4.9-winx64"
set "DB_SQL=C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_db.sql"
"%MYSQL_HOME%\bin\mysql.exe" --host=127.0.0.1 --port=3306 --user=root < "%DB_SQL%"
if %errorlevel%==0 (
  echo Base de datos importada correctamente.
) else (
  echo Error importando la base de datos.
)
