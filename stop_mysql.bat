@echo off
setlocal
set "MYSQL_HOME=C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\mysql-8.4.9-winx64"
"%MYSQL_HOME%\bin\mysqladmin.exe" --host=127.0.0.1 --port=3306 --user=root shutdown
