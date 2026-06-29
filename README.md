# Inmobiliary-Data Bot

Bot automatico para recolectar publicaciones de venta de inmuebles ubicados en Pasto, Narino, desde las fuentes autorizadas del proyecto.

## Que hace

- Escanea automaticamente Facebook Marketplace, Metrocuadrado, Ciencuadras, FincaRaiz y Clasificados Amorel.
- Registra publicaciones nuevas en MySQL.
- Actualiza publicaciones ya existentes sin borrar datos anteriores.
- Guarda historial de precios.
- Guarda imagenes optimizadas en `.webp`.
- Guarda evidencias HTML/capturas cuando sea posible.
- Registra cada escaneo y sus resultados.
- Solo trabaja con ventas ubicadas en Pasto.
- Descarta arriendos y publicaciones fuera de Pasto.
- Si una publicacion de Pasto viene incompleta, la guarda como `pendiente_revision`.

## Rutas importantes

Proyecto del bot:

```text
C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot
```

SQL de la base de datos:

```text
C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_db.sql
```

MySQL portable instalado:

```text
C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\mysql-8.4.9-winx64
```

Frontend:

```text
http://127.0.0.1:3000
```

## Primera ejecucion

Abre PowerShell y ejecuta:

```powershell
cd C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot
.\install.bat
.\start_mysql.bat
.\import_db.bat
.\start_sistema.bat
```

Luego abre:

```text
http://127.0.0.1:3000
```

## Ejecucion normal

Despues de la primera configuracion, normalmente solo necesitas:

```powershell
cd C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot
.\start_sistema.bat
```

Ese comando levanta MySQL si hace falta y arranca el frontend. El frontend arranca tambien el bot automatico.

## Bot automatico

El bot automatico se configura en:

```text
C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot\.env
```

Configuracion actual:

```env
BOT_AUTO_SCAN=true
BOT_SCAN_ON_START=true
BOT_SCAN_INTERVAL_MINUTES=30
BOT_MAX_PAGES=0
BOT_MAX_LISTINGS_PER_SOURCE=0
```

Significado:

- `BOT_AUTO_SCAN=true`: el bot queda activo automaticamente.
- `BOT_SCAN_ON_START=true`: escanea apenas se inicia el sistema.
- `BOT_SCAN_INTERVAL_MINUTES=30`: repite el escaneo cada 30 minutos.
- `BOT_MAX_PAGES=0`: no limita cantidad de paginas.
- `BOT_MAX_LISTINGS_PER_SOURCE=0`: no limita cantidad de publicaciones.

## Inicio automatico con Windows

Para que el bot arranque cuando abras sesion en Windows:

```powershell
cd C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot
.\registrar_inicio_automatico.bat
```

Para quitar ese inicio automatico:

```powershell
cd C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot
.\eliminar_inicio_automatico.bat
```

El inicio automatico queda registrado en:

```text
C:\Users\qalej\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\InmobiliaryDataBot.bat
```

## Detener el sistema

Para detener frontend/bot y MySQL:

```powershell
cd C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot
.\stop_sistema.bat
```

Para detener solo MySQL:

```powershell
.\stop_mysql.bat
```

## Escaneo manual

Aunque el bot escanea solo, tambien puedes ejecutar un escaneo completo manual:

```powershell
cd C:\Users\qalej\Documents\Codex\2026-06-27\a\outputs\inmobiliary_bot
.\run_bot.bat
```

Escanear una sola fuente:

```powershell
node src/cli.js scan --source fincaraiz
node src/cli.js scan --source metrocuadrado
node src/cli.js scan --source ciencuadras
node src/cli.js scan --source amorel
node src/cli.js scan --source facebook
```

## Verificar que funciona

Revisar salud del servidor:

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/health
```

Revisar estado del bot:

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/bot/status
```

Revisar conteos en MySQL:

```powershell
C:\Users\qalej\Documents\Codex\2026-06-27\a\work\mysql\mysql-8.4.9-winx64\bin\mysql.exe --host=127.0.0.1 --port=3306 --user=root --database=inmobiliary_data --execute="SELECT COUNT(*) publicaciones FROM publicaciones; SELECT COUNT(*) inmuebles FROM inmuebles; SELECT COUNT(*) imagenes FROM imagenes; SELECT COUNT(*) escaneos FROM escaneos;"
```

## Archivos utiles

- `start_sistema.bat`: inicia MySQL, frontend y bot automatico.
- `stop_sistema.bat`: detiene frontend/bot y MySQL.
- `start_mysql.bat`: inicia solo MySQL.
- `stop_mysql.bat`: detiene solo MySQL.
- `import_db.bat`: importa la estructura de la BD.
- `run_bot.bat`: ejecuta un escaneo completo manual.
- `start_front.bat`: inicia solo el frontend/API.
- `registrar_inicio_automatico.bat`: registra arranque automatico al iniciar sesion.
- `eliminar_inicio_automatico.bat`: elimina el arranque automatico.

## Solucion de problemas

Error `connect ECONNREFUSED 127.0.0.1:3306`:

```powershell
.\start_mysql.bat
```

Error `La base de datos inmobiliary_data no existe`:

```powershell
.\import_db.bat
```

El navegador no carga `http://127.0.0.1:3000`:

```powershell
.\start_sistema.bat
```

Facebook Marketplace puede pedir sesion. El bot no guarda contrasenas ni evade login. Si se necesita una sesion autorizada, configura `FACEBOOK_STORAGE_STATE` en `.env`.

## Notas

- La base de datos no usa vistas.
- El frontend consulta tablas directamente.
- Las publicaciones guardadas se conservan; el bot actualiza registros existentes en lugar de borrarlos.
- Las imagenes quedan en `storage/imagenes`.
- Las evidencias quedan en `storage/evidencias`.
