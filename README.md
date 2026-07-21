# inmobiliary-data

Scrapers de inmuebles **en venta en Pasto** desde cinco portales, con detección
de duplicados, normalización de barrios y un front de Next.js sobre la misma
base MySQL.

| Portal | Módulo |
|---|---|
| Finca Raíz | `inmobiliary.scrapers.fincaraiz` |
| Metrocuadrado | `inmobiliary.scrapers.metrocuadrado` |
| Ciencuadras | `inmobiliary.scrapers.ciencuadras` |
| Amorel | `inmobiliary.scrapers.amorel` |
| Facebook Marketplace | `inmobiliary.scrapers.facebook` |

---

## Estructura

```
src/inmobiliary/        paquete Python
├─ config.py            conexión a MySQL (falla si no hay DB_PASSWORD)
├─ common.py            utilidades compartidas: texto, archivos, capa de BD
├─ net.py               reintentos con backoff
├─ audit.py             auditoría de cada corrida (queda en logs/)
├─ detectors/
│  ├─ duplicates.py     detección de inmuebles repetidos entre portales
│  ├─ location.py       normalización de barrios y veredas
│  └─ ph.py             detección de propiedad horizontal
└─ scrapers/            un módulo por portal
scripts/                migraciones, backfills, seed de catálogos
db/
├─ schema/              esquema base
├─ migrations/          migraciones numeradas + sus reversas
└─ queries/             consultas sueltas
tests/                  71 pruebas (no necesitan MySQL ni Playwright)
docs/                   documentación
front/                  aplicación Next.js
data/                   catálogo de barrios y veredas de Pasto
```

---

## Instalación

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m playwright install chromium
py -3 -m pip install -e .
```

`pip install -e .` deja el paquete importable desde cualquier carpeta. Si
preferís no instalarlo, definí `PYTHONPATH=src` antes de cada comando.

Para desarrollo y pruebas:

```powershell
py -3 -m pip install -r requirements-dev.txt
```

---

## Configuración

Copiá `.env.example` a `.env` y completá. **`DB_PASSWORD` es obligatoria**: los
scripts se detienen con un error claro si falta. No hay contraseña por defecto.

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=tu_clave_mysql
DB_NAME=db_inmobiliary_data
```

El front necesita las mismas variables en `front/.env.local`.

> **Facebook usa el puerto 3301 por defecto**, no 3306. Si tu MySQL corre en
> otro puerto, definí `DB_PORT` explícitamente.

---

## Base de datos

### Crear desde cero

```powershell
# 1. Crear la base
mysql -u root -p -e "CREATE DATABASE db_inmobiliary_data CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 2. Esquema base: 7 tablas
mysql -u root -p db_inmobiliary_data < db/schema/inmobiliary_db.sql

# 3. Migraciones (idempotentes, se pueden repetir sin riesgo)
py -3 scripts/apply_duplicate_migration.py
py -3 scripts/apply_catalogos_migration.py

# 4. Poblar catálogos de barrios y tipos de inmueble
py -3 scripts/seed_catalogos.py
```

### Tablas

| Tabla | Origen | Qué guarda |
|---|---|---|
| `fuentes_inmobiliarias` | esquema base | Un registro por portal |
| `publicaciones` | esquema base | El aviso tal como lo publicó el portal |
| `evidencias_publicacion` | esquema base | HTML, capturas e imágenes + su hash SHA-256 |
| `inmuebles_detectados` | migración 001 | Inmueble real deducido de varias publicaciones |
| `publicaciones_inmueble` | migración 001 | Relación publicación ↔ inmueble |
| `imagenes_hashes` | migración 001 | Hashes para comparar fotos entre portales |
| `coincidencias_publicaciones` | migración 001 | Pares candidatos a duplicado y su puntaje |
| `barrios` | migración 003 | Catálogo de barrios y veredas de Pasto |
| `tipos_inmueble` | migración 003 | Catálogo de tipos |

### Migraciones

| Archivo | Qué hace |
|---|---|
| `001_duplicate_detection.sql` | Crea las 4 tablas del detector de duplicados |
| `002_exact_image_hash.sql` | Agrega el hash SHA-256 exacto a las imágenes |
| `003_catalogos_ubicacion_tipo.sql` | Crea `barrios` y `tipos_inmueble` |

Cada una tiene su `_down.sql` para revertirla. Los scripts `apply_*` son
**idempotentes**: si las tablas ya existen no hacen nada y lo informan.

### Revertir

```powershell
mysql -u root -p db_inmobiliary_data < db/migrations/003_catalogos_ubicacion_tipo_down.sql
mysql -u root -p db_inmobiliary_data < db/migrations/001_duplicate_detection_down.sql
```

---

## Guía de comandos

### Scrapers

```powershell
py -3 -m inmobiliary.scrapers.fincaraiz
py -3 -m inmobiliary.scrapers.metrocuadrado
py -3 -m inmobiliary.scrapers.ciencuadras
py -3 -m inmobiliary.scrapers.amorel
py -3 -m inmobiliary.scrapers.facebook
```

### Scripts operativos

| Comando | Qué hace |
|---|---|
| `py -3 scripts/apply_duplicate_migration.py` | Aplica migraciones 001 y 002 |
| `py -3 scripts/apply_catalogos_migration.py` | Aplica migración 003 |
| `py -3 scripts/seed_catalogos.py` | Puebla `barrios` y `tipos_inmueble` |
| `py -3 scripts/backfill_duplicate_detection.py` | Reanaliza duplicados en publicaciones ya guardadas |
| `py -3 scripts/backfill_location_normalization.py` | Renormaliza los barrios ya guardados |

### Pruebas

```powershell
py -3 -m pytest -q               # las 71
py -3 -m pytest -q -k parsers    # solo los extractores
```

No necesitan MySQL, Playwright ni conexión a los portales.

### Front

```powershell
cd front
pnpm install
pnpm dev
```

Corre en `http://localhost:3001`. El botón de escanear ejecuta los scrapers con
`python -m` e inyecta `PYTHONPATH=src`, así que funciona aunque no hayas hecho
`pip install -e .`. Con `SCRAPER_PYTHON` podés forzar otro intérprete.

---

## Variables de entorno

### Conexión (todas las herramientas)

| Variable | Defecto | Notas |
|---|---|---|
| `DB_HOST` | `localhost` | |
| `DB_PORT` | `3306` | Facebook usa `3301` si no la definís |
| `DB_USER` | `root` | |
| `DB_PASSWORD` | — | **Obligatoria**, sin valor por defecto |
| `DB_NAME` | `db_inmobiliary_data` | |

### Reintentos de red (todos los scrapers)

| Variable | Defecto | Notas |
|---|---|---|
| `RETRY_ATTEMPTS` | `3` | Intentos antes de descartar |
| `RETRY_BASE_DELAY_SECONDS` | `2` | Backoff exponencial: 2s, 4s, 8s |

### Comunes a los scrapers de navegador

| Variable | Defecto |
|---|---|
| `HEADLESS` | `true` |
| `MAX_PAGES` | `0` (todas) |
| `IMAGE_DOWNLOAD_WORKERS` | `6` |
| `IMAGE_DOWNLOAD_TIMEOUT` | `12` |
| `REQUEST_PAUSE_SECONDS` | `0.5` |
| `SEARCH_LOAD_WAIT_MS` | `2500` |
| `DETAIL_LOAD_WAIT_MS` | `1200` |
| `SCROLL_WAIT_MS` | `1000` |

### Detección de duplicados

| Variable | Defecto | Notas |
|---|---|---|
| `DUPLICATE_DETECTION_ENABLED` | `true` | |
| `DUPLICATE_AUTO_THRESHOLD` | `80` | Puntaje para unir automáticamente |
| `DUPLICATE_REVIEW_THRESHOLD` | `60` | Puntaje para marcar como "revisar" |
| `DUPLICATE_MAX_DISTANCE_METERS` | `100` | Radio para considerar el mismo inmueble |
| `DUPLICATE_MIN_IMAGE_WIDTH` | `200` | Descarta íconos y logos |
| `DUPLICATE_MIN_IMAGE_HEIGHT` | `150` | |
| `DUPLICATE_BACKFILL_BATCH_SIZE` | `100` | Lote del backfill |

### Por portal

**Finca Raíz**

| Variable | Defecto |
|---|---|
| `FINCARAIZ_SEARCH_URL` | `https://www.fincaraiz.com.co/venta/pasto/narino` |
| `MIN_PHOTO_AREA` | `22500` (150×150) |

**Metrocuadrado**

| Variable | Defecto |
|---|---|
| `METROCUADRADO_SEARCH_URL` | listado de venta en Pasto |
| `METROCUADRADO_LIST_SCROLLS` | `8` |
| `METROCUADRADO_STALL_SCROLLS` | `3` |
| `MAX_PUBLICATIONS` | `0` (todas) |
| `DOWNLOAD_IMAGES` | `true` |
| `PUBLICATION_URL` | — (procesa una sola publicación) |

**Ciencuadras**

| Variable | Defecto |
|---|---|
| `GALLERY_VISIBLE_WAIT_MS` | `400` |
| `GALLERY_OPEN_WAIT_MS` | `600` |
| `GALLERY_CLICK_WAIT_MS` | `250` |
| `GALLERY_STALLED_CLICKS` | `2` |
| `GALLERY_MAX_NEXT_CLICKS` | `40` |
| `PAGINATION_LOAD_WAIT_MS` | `2000` |

**Amorel**

| Variable | Defecto |
|---|---|
| `AMOREL_SEARCH_URL` | listado de Finca Raíz de Amorel |
| `AMOREL_MAX_PAGES` | `0` (todas) |
| `AMOREL_PAGE_PAUSE_SECONDS` | `0.3` |
| `AMOREL_MIN_SALE_PRICE` | `10000000` |

**Facebook Marketplace** — ver sección dedicada abajo.

---

## Facebook Marketplace

Usa Playwright con un perfil persistente en `.facebook_profile/`. En el primer
uso abre Chromium y puede pedir login, 2FA o captcha; después reutiliza esa
sesión local.

### Modo incremental

Si la fuente ya tiene publicaciones guardadas, la corrida es **incremental**:
usa un solo listado ordenado por más reciente y corta al encontrar varios links
seguidos que ya están en la base. Si la fuente está vacía, hace el **barrido
completo** por rangos de precio (17 listados).

Esto reduce los scrolls de 1360 a 80 en corridas sucesivas.

### Prueba sin guardar

```powershell
$env:FACEBOOK_DRY_RUN="true"
$env:FACEBOOK_MAX_DETAILS="5"
$env:FACEBOOK_MAX_SCROLLS="8"
py -3 -m inmobiliary.scrapers.facebook
```

En dry-run **lee** la base para decidir el modo y saltear links conocidos, pero
nunca escribe. Si MySQL no está disponible, avisa y hace barrido completo.

### Ejecución real

```powershell
$env:FACEBOOK_DRY_RUN="false"
py -3 -m inmobiliary.scrapers.facebook
```

### Variables

| Variable | Defecto | Notas |
|---|---|---|
| `FACEBOOK_DRY_RUN` | `false` | No guarda nada en MySQL |
| `FACEBOOK_HEADLESS` | `false` | En `false` podés resolver login y captcha |
| `FACEBOOK_FULL_SWEEP` | `false` | Fuerza el barrido completo por precio |
| `FACEBOOK_CONSECUTIVE_EXISTING_LIMIT` | `5` | Links ya guardados seguidos que cortan un listado |
| `FACEBOOK_MARKETPLACE_URLS` | — | URLs completas separadas por `;` o `\|` |
| `FACEBOOK_SEARCH_PHRASES` | — | Modo alternativo: busca por frases |
| `FACEBOOK_SEARCH_CITY` | `pasto` | Solo en el modo por frases |
| `FACEBOOK_SEARCH_CATEGORY` | `homesales` | |
| `FACEBOOK_SEARCH_RADIUS` | — | |
| `FACEBOOK_DATE_LISTED_DAYS` | — | |
| `FACEBOOK_MIN_PRICE` / `FACEBOOK_MAX_PRICE` | — | |
| `FACEBOOK_PRICE_BUCKETS` | 16 rangos | Personalizados: `0-80000000;80000000-120000000;3000000000+` |
| `FACEBOOK_SPLIT_PRICE_BUCKETS` | `true` | Recorre por rangos para superar el techo de resultados |
| `FACEBOOK_INCLUDE_UNFILTERED_LISTING` | `true` | Revisa primero el listado general |
| `FACEBOOK_MAX_SCROLLS` | `80` | Scrolls máximos por listado |
| `FACEBOOK_STALL_SCROLLS` | `4` | Corta tras N scrolls sin links nuevos |
| `FACEBOOK_MAX_LINKS` | `0` (sin tope) | |
| `FACEBOOK_MAX_DETAILS` | `0` (sin tope) | |
| `FACEBOOK_MAX_IMAGES_PER_LISTING` | `12` | |
| `FACEBOOK_MIN_SALE_PRICE` | `10000000` | Evita guardar números que no son precio |
| `FACEBOOK_TRUST_SALE_FILTERS` | `true` | Igual rechaza arriendo y exige precio real |
| `FACEBOOK_SCROLL_PAUSE_SECONDS` | `2.5` | |
| `FACEBOOK_PAGE_TIMEOUT_MS` | `45000` | |
| `FACEBOOK_LOGIN_WAIT_SECONDS` | `90` | Espera para login manual |
| `FACEBOOK_USER_DATA_DIR` | `.facebook_profile` | |
| `FACEBOOK_SESSION_COOKIES_PATH` | — | |

### Qué se guarda y qué se descarta

Se guardan publicaciones con precio y tipo de inmueble reconocido. Se rechaza
arriendo, alquiler, renta, anticresis, permuta, busco/compro y anuncios
explícitamente fuera de Pasto. Las imágenes salen del bloque de la publicación,
descartando fotos de perfiles y publicaciones relacionadas. La auditoría de cada
corrida queda en `logs/`.

Si un listado se queda alrededor de 500 resultados, mantené activa la división
por precio: Facebook limita cada scroll infinito, no el total disponible.

### Validación de links desde el front

El front verifica si el `link_origen` de cada publicación sigue activo. Para
Facebook, un `fetch` sin sesión siempre choca con el muro de login, así que el
scraper exporta las cookies de la sesión activa a
`.facebook_profile/session_cookies.json` (se sobrescriben en cada corrida,
apenas se confirma que la sesión sigue logueada). El front las lee desde ahí.

---

## Documentación adicional

- [docs/DUPLICATE_DETECTION.md](docs/DUPLICATE_DETECTION.md) — cómo funciona la
  detección de inmuebles repetidos entre portales.
