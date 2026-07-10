# Instalar dependencias
pip install playwright mysql-connector-python python-dotenv requests beautifulsoup4
python -m playwright install chromium

## Configuración compartida

El bot de Python y el front de Next.js usan la misma base de datos MySQL.

Variables esperadas:

- `DB_HOST=localhost`
- `DB_PORT=3306`
- `DB_USER=root`
- `DB_PASSWORD=...`
- `DB_NAME=db_inmobiliary_data`

En el front, crea un archivo `front/.env.local` con esas variables antes de ejecutar `pnpm dev`.

El front corre por defecto en `http://localhost:3001`.

## Scraper Facebook Marketplace

El scraper `scraper_facebook_marketplace.py` usa Playwright con un perfil persistente en `.facebook_profile/`. En el primer uso puede abrir Chromium y pedir login, 2FA o captcha; despues reutiliza esa sesion local.

Prueba sin guardar en MySQL:

```powershell
$env:FACEBOOK_DRY_RUN="true"
$env:FACEBOOK_MAX_DETAILS="5"
$env:FACEBOOK_MAX_SCROLLS="8"
python scraper_facebook_marketplace.py
```

Ejecucion real:

```powershell
$env:FACEBOOK_DRY_RUN="false"
python scraper_facebook_marketplace.py
```

Variables utiles:

- `FACEBOOK_MARKETPLACE_URLS`: una o varias URLs completas de busqueda separadas por `;` o `|`.
- `FACEBOOK_SEARCH_CITY=pasto`: ciudad usada si no pasas URLs completas.
- `FACEBOOK_SEARCH_PHRASES`: frases separadas por `;` o `|`; por defecto busca ventas de casa, apartamento, lote, oficina, local y finca en Pasto.
- `FACEBOOK_HEADLESS=false`: recomendado para resolver login/captcha manualmente.
- `FACEBOOK_LOGIN_WAIT_SECONDS=90`: espera para completar login manual.
- `FACEBOOK_MAX_SCROLLS=30`: scrolls por busqueda.
- `FACEBOOK_STALL_SCROLLS=4`: detiene una busqueda tras varios scrolls sin links nuevos.
- `FACEBOOK_MIN_SALE_PRICE=10000000`: evita guardar numeros pequenos que no son precio real.

El filtro guarda solo publicaciones de venta con precio y tipo de inmueble reconocido. Rechaza arriendo, alquiler, renta, anticresis, permuta, busco/compro y anuncios explicitamente fuera de Pasto. La auditoria queda en `logs/`.

Si aparece `Access denied for user 'root'@'localhost'`, MySQL rechazo la clave usada por el scraper. Define la misma clave que usas para entrar a tu MySQL:

```powershell
$env:DB_HOST="localhost"
$env:DB_PORT="3306"
$env:DB_USER="root"
$env:DB_PASSWORD="tu_clave_mysql"
$env:DB_NAME="db_inmobiliary_data"
python scraper_facebook_marketplace.py
```
