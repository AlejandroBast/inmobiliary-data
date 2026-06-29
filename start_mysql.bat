@echo off
setlocal
set "MYSQL_HOME=C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\mysql-8.4.9-winx64"
set "MYSQL_CNF=C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\my.ini"
start "Inmobiliary MySQL" /min "%MYSQL_HOME%\bin\mysqld.exe" --defaults-file="%MYSQL_CNF%"
echo MySQL iniciado en 127.0.0.1:3306
