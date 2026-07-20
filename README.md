# inmobiliary-data

Scrapers de inmuebles en venta en Pasto (Fincaraíz, Metrocuadrado, Ciencuadras,
Amorel, Facebook Marketplace) + front de Next.js sobre la misma base MySQL.

## Estructura

```
src/inmobiliary/        paquete Python
├─ config.py            configuracion de conexion a MySQL
├─ common.py            utilidades compartidas (texto, archivos, capa de BD)
├─ net.py               reintentos con backoff
├─ audit.py             auditoria de corridas
├─ detectors/           duplicados, ubicacion, propiedad horizontal
└─ scrapers/            un modulo por portal
scripts/                migraciones, backfills, seed de catalogos
db/                     schema/, migrations/, queries/
tests/                  pruebas (no necesitan MySQL ni Playwright)
docs/                   documentacion
front/                  aplicacion Next.js
data/                   catalogo de barrios y veredas de Pasto
```

# Instalar dependencias
py -3 -m pip install -r requirements.txt
py -3 -m playwright install chromium
py -3 -m pip install -e .

El `pip install -e .` deja el paquete importable desde cualquier carpeta. Si
preferis no instalarlo, defini `PYTHONPATH=src` antes de ejecutar.

## Ejecutar un scraper

Los scrapers son modulos del paquete, se ejecutan con `-m` desde la raiz:

```powershell
py -3 -m inmobiliary.scrapers.fincaraiz
py -3 -m inmobiliary.scrapers.metrocuadrado
py -3 -m inmobiliary.scrapers.ciencuadras
py -3 -m inmobiliary.scrapers.amorel
py -3 -m inmobiliary.scrapers.facebook
```

## Scripts operativos

```powershell
py -3 scripts/apply_duplicate_migration.py
py -3 scripts/apply_catalogos_migration.py
py -3 scripts/seed_catalogos.py
py -3 scripts/backfill_duplicate_detection.py
py -3 scripts/backfill_location_normalization.py
```

## Pruebas

```powershell
py -3 -m pip install -r requirements-dev.txt
py -3 -m pytest tests/ -q
```

No necesitan Playwright, MySQL ni conexión a los portales.

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

El scraper `inmobiliary.scrapers.facebook` usa Playwright con un perfil persistente en `.facebook_profile/`. En el primer uso puede abrir Chromium y pedir login, 2FA o captcha; despues reutiliza esa sesion local.

Prueba sin guardar en MySQL:

```powershell
$env:FACEBOOK_DRY_RUN="true"
$env:FACEBOOK_MAX_DETAILS="5"
$env:FACEBOOK_MAX_SCROLLS="8"
py -3 -m inmobiliary.scrapers.facebook
```

Ejecucion real:

```powershell
$env:FACEBOOK_DRY_RUN="false"
py -3 -m inmobiliary.scrapers.facebook
```

Variables utiles:

- `FACEBOOK_MARKETPLACE_URLS`: una o varias URLs completas de busqueda separadas por `;` o `|`.
- Si no defines `FACEBOOK_MARKETPLACE_URLS`, el scraper usa por defecto el listado filtrado de Facebook Marketplace para `Viviendas en venta` en Pasto.
- `FACEBOOK_SEARCH_PHRASES`: modo opcional para volver a busquedas por frases separadas por `;` o `|`.
- `FACEBOOK_SEARCH_CITY=pasto`: ciudad usada solo en el modo opcional de busquedas por frases.
- `FACEBOOK_HEADLESS=false`: recomendado para resolver login/captcha manualmente.
- `FACEBOOK_LOGIN_WAIT_SECONDS=90`: espera para completar login manual.
- `FACEBOOK_MAX_SCROLLS=80`: scrolls maximos por listado.
- `FACEBOOK_STALL_SCROLLS=4`: detiene un listado tras varios scrolls sin links nuevos.
- `FACEBOOK_TRUST_SALE_FILTERS=true`: confia en que el listado filtrado ya es de venta; igual rechaza arriendo/alquiler y exige precio real.
- `FACEBOOK_SPLIT_PRICE_BUCKETS=true`: recorre el mismo listado por rangos de precio para superar el techo practico de resultados que Facebook entrega en un solo scroll.
- `FACEBOOK_INCLUDE_UNFILTERED_LISTING=true`: primero revisa el listado general y luego los rangos de precio.
- `FACEBOOK_PRICE_BUCKETS`: rangos personalizados separados por `;`, por ejemplo `0-80000000;80000000-120000000;120000000-160000000;3000000000+`.
- `FACEBOOK_MIN_SALE_PRICE=10000000`: evita guardar numeros pequenos que no son precio real.

El filtro guarda publicaciones con precio y tipo de inmueble reconocido. Rechaza arriendo, alquiler, renta, anticresis, permuta, busco/compro y anuncios explicitamente fuera de Pasto. Las imagenes se extraen desde el bloque de la publicacion y se descartan fotos de perfiles o publicaciones relacionadas. La auditoria queda en `logs/`. Si un solo listado se queda alrededor de 500 resultados, manten activa la division por precio; Facebook suele limitar cada scroll infinito, no necesariamente el total real disponible.

### Validacion de links de Facebook en el front

El front verifica si el `link_origen` de cada publicacion sigue activo. Para links de Facebook, un simple `fetch` sin sesion siempre choca con el muro de login, asi que el scraper exporta las cookies de la sesion activa a `.facebook_profile/session_cookies.json` (se sobreescriben en cada corrida, apenas se confirma que la sesion sigue logueada). El front las lee desde ahi para validar esos links con la misma sesion.

- Si nunca corriste el scraper con sesion valida, o el archivo no existe, esos links se muestran como "No verificable (sesion Facebook)" en vez de marcarse en rojo.
- Si la sesion expiro, corre el scraper una vez (aunque sea con `FACEBOOK_DRY_RUN=true`) para refrescarla.
- Ruta configurable con `FACEBOOK_SESSION_COOKIES_PATH` (debe apuntar al mismo archivo desde ambos lados, Python y `front/.env.local`).

Si aparece `Access denied for user 'root'@'localhost'`, MySQL rechazo la clave usada por el scraper. Define la misma clave que usas para entrar a tu MySQL:

```powershell
$env:DB_HOST="localhost"
$env:DB_PORT="3306"
$env:DB_USER="root"
$env:DB_PASSWORD="tu_clave_mysql"
$env:DB_NAME="db_inmobiliary_data"
py -3 -m inmobiliary.scrapers.facebook
```
