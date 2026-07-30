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
tests/                  125 pruebas (no necesitan MySQL ni Playwright)
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

# 2. Esquema base: incluye barrios y tipos_inmueble (antes migración 003,
#    fusionada aca para que un reinicio de la base no las deje sin crear)
mysql -u root -p db_inmobiliary_data < db/schema/inmobiliary_db.sql

# 3. Migraciones (idempotentes, se pueden repetir sin riesgo; ya no hace
#    falta apply_catalogos_migration.py, queda solo por compatibilidad)
py -3 scripts/apply_duplicate_migration.py

# 4. Poblar catálogos de barrios y tipos de inmueble
py -3 scripts/seed_catalogos.py --apply
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
| `barrios` | esquema base (antes migración 003) | Catálogo de barrios y veredas de Pasto |
| `tipos_inmueble` | esquema base (antes migración 003) | Catálogo de tipos |

### Migraciones

| Archivo | Qué hace |
|---|---|
| `001_duplicate_detection.sql` | Crea las 4 tablas del detector de duplicados |
| `002_exact_image_hash.sql` | Agrega el hash SHA-256 exacto a las imágenes |
| `003_catalogos_ubicacion_tipo.sql` | Crea `barrios` y `tipos_inmueble` (ya fusionado en el esquema base; este archivo queda solo para bases muy viejas) |

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
py -3 -m pytest -q               # las 125
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
| `DUPLICATE_PERCEPTUAL_MAX_DISTANCE` | `6` | Distancia dHash máxima para tratar dos fotos como la misma |
| `DUPLICATE_PRICE_MAX_DIFFERENCE` | `0.30` | Brecha de precio desde la cual se penaliza el par |

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

### Por dónde entra

El listado de **Inmuebles de Pasto**, con la URL tal como la deja Marketplace al
aplicar los filtros desde su propia interfaz:

```
https://www.facebook.com/marketplace/108037152563666/search
    ?query=Inmuebles&category_id=1270772586445798&exact=false
    &referral_ui_component=category_menu_item
    &sortBy=creation_time_descend&daysSinceListed=30&radius=20
```

| Parte | Por qué |
|---|---|
| `108037152563666` | ID de la página de ubicación de Pasto. Es el mismo que Facebook devuelve en `reverse_geocode.city_page.id` al geocodificar un aviso, así que se verifica contra cualquier evidencia guardada |
| `query=Inmuebles` + `category_id` | La categoría Inmuebles. Antes se buscaba `query=Viviendas en venta`, que dependía de que el título del aviso trajera esas palabras (se perdían avisos como "SE VENDA CASA") |
| `exact=false` | Deja que Facebook amplíe la coincidencia del texto |
| `daysSinceListed` | 30 la primera corrida, 7 las siguientes. Marketplace solo acepta `1`, `7` y `30` |
| `radius=20` | **Lo único que agrega el scraper.** La URL del navegador no lo trae porque Facebook recuerda el radio por sesión; mandarlo explícito evita depender de esa preferencia guardada. Se quita con `FACEBOOK_SEARCH_RADIUS=` |

> **No se ordena por más reciente.** `sortBy=creation_time_descend` parece cambiar
> el modo de resultados de Marketplace: deja de mostrar el encabezado
> "Resultados relacionados fuera de tu búsqueda" —que es el corte del scroll— y
> sigue sirviendo avisos cada vez más lejanos sin límite. Con él la corrida se iba
> a **más de mil** publicaciones donde la UI muestra **59**. Se activa con
> `FACEBOOK_SORT_BY_NEWEST=true`.
>
> Como consecuencia, el corte por `FACEBOOK_CONSECUTIVE_EXISTING_LIMIT` **solo se
> aplica si el orden es por fecha**: sin ese orden, unos links ya guardados no
> significan que lo que sigue sea más viejo, y cortar ahí perdería avisos. Los
> links ya guardados se saltean igual, para no reabrir su página de detalle.

`FACEBOOK_MARKETPLACE_URLS` sigue pisando esto si querés apuntar a otra búsqueda;
los filtros de las últimas tres filas se le aplican igual.

### Modo incremental

Si la fuente ya tiene publicaciones guardadas, la corrida es **incremental**:
usa un solo listado ordenado por más reciente y corta al encontrar varios links
seguidos que ya están en la base. Si la fuente está vacía, hace el **barrido
completo** por rangos de precio (17 listados).

Esto reduce los scrolls de 1360 a 80 en corridas sucesivas.

### Ventana de antigüedad

Ningún modo recorre el histórico completo: se usa el filtro *Fecha de
publicación* de Marketplace (`daysSinceListed`) en **todos** los listados.

| Corrida | Ventana | Variable |
|---|---|---|
| Primera (fuente vacía o `FACEBOOK_FULL_SWEEP`) | últimos **30 días** | `FACEBOOK_FIRST_RUN_DAYS` |
| Todas las siguientes (incremental) | últimos **7 días** | `FACEBOOK_INCREMENTAL_DAYS` |

Traer todo de una sola vez es lo que provocaba la **restricción temporal de la
cuenta** alrededor de las 300 publicaciones recolectadas: la ventana recorta
tanto los scrolls del listado como las visitas a páginas de detalle.

Además hay un **tope de 50 avisos por corrida** (`FACEBOOK_MAX_LINKS`): se toman
las 50 primeras del listado y ahí se deja de scrollear. Es el límite más efectivo
contra la restricción, porque acota de una vez las dos cosas que gastan requests.
El tope cuenta **links recolectados**, no guardados: de esos 50, los que sean
arriendo, no tengan precio o estén fuera de Pasto se descartan después, así que
en la base quedan menos de 50.

Marketplace solo respeta `1`, `7` y `30` en ese filtro; con otro valor ignora el
filtro y devuelve el listado entero. El scraper avisa con `[WARN]` si le pasás
uno distinto, pero lo usa igual.

`FACEBOOK_DATE_LISTED_DAYS` pisa la ventana en los dos modos. En `0` se
recolecta sin filtro de fecha (el comportamiento viejo), útil para una corrida
de recuperación puntual:

```powershell
$env:FACEBOOK_DATE_LISTED_DAYS="30"   # ponerse al día tras más de 7 días sin correr
py -3 -m inmobiliary.scrapers.facebook
```

> Si dejás pasar **más de 7 días** entre corridas, las publicaciones de ese
> hueco no se recogen. Para recuperarlas, corré una vez con
> `FACEBOOK_DATE_LISTED_DAYS=30`.

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
| `FACEBOOK_SKIP_NON_PASTO_CARDS` | `true` | Descarta desde el listado los avisos cuya tarjeta declara otra ciudad, sin abrirlos |
| `FACEBOOK_CONSECUTIVE_OUTSIDE_LIMIT` | `25` | Tarjetas seguidas de otra ciudad que cortan un listado (`0` desactiva) |
| `FACEBOOK_SEARCH_RADIUS` | `20` | Radio en km alrededor de Pasto; vacío lo quita |
| `FACEBOOK_SORT_BY_NEWEST` | `false` | Ordena por más reciente. Rompe el corte por encabezado (ver arriba) |
| `FACEBOOK_MARKETPLACE_URLS` | — | URLs completas separadas por `;` o `\|` |
| `FACEBOOK_SEARCH_PHRASES` | — | Modo alternativo: busca por frases |
| `FACEBOOK_SEARCH_CITY` | `pasto` | Solo en el modo por frases |
| `FACEBOOK_SEARCH_CATEGORY` | `homesales` | |
| `FACEBOOK_SEARCH_RADIUS` | — | |
| `FACEBOOK_FIRST_RUN_DAYS` | `30` | Ventana de la primera corrida / barrido completo |
| `FACEBOOK_INCREMENTAL_DAYS` | `7` | Ventana de las corridas incrementales |
| `FACEBOOK_DATE_LISTED_DAYS` | — | Pisa la ventana en los dos modos; `0` = sin filtro de fecha |
| `FACEBOOK_MIN_PRICE` / `FACEBOOK_MAX_PRICE` | — | |
| `FACEBOOK_PRICE_BUCKETS` | 16 rangos | Personalizados: `0-80000000;80000000-120000000;3000000000+` |
| `FACEBOOK_SPLIT_PRICE_BUCKETS` | `true` | Recorre por rangos para superar el techo de resultados |
| `FACEBOOK_INCLUDE_UNFILTERED_LISTING` | `true` | Revisa primero el listado general |
| `FACEBOOK_MAX_SCROLLS` | `80` | Scrolls máximos por listado |
| `FACEBOOK_STALL_SCROLLS` | `4` | Corta tras N scrolls sin links nuevos |
| `FACEBOOK_MAX_LINKS` | `50` | Corta al juntar las primeras 50 del listado. `0` = sin tope |
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
arriendo, alquiler, renta, anticresis, permuta, busco/compro y anuncios fuera de
Pasto.

El descarte por municipio ocurre en **tres etapas**:

0. **Cortando el scroll** donde Facebook dice que se terminó la búsqueda (ver
   abajo). Es lo que más reduce el volumen.
1. **En el listado, sin abrir el aviso.** La tarjeta ya muestra la ubicación
   (`Fusagasugá, Cundinamarca`). Si el departamento no es Nariño, o es Nariño
   pero el municipio no es Pasto, el link se descarta ahí mismo. Esto es lo que
   baja el volumen de visitas —y con él el riesgo de restricción—: el barrido de
   30 días llega a recolectar **más de 3000 links**, la enorme mayoría de fuera
   de Pasto, porque el radio de Marketplace no respeta el límite municipal. Es
   deliberadamente conservador: si la tarjeta no trae una ubicación reconocible,
   el aviso se abre igual. Se desactiva con `FACEBOOK_SKIP_NON_PASTO_CARDS=false`.
2. **En la página de detalle**, con el texto completo, para lo que sobrevivió.

### Por qué aparecían avisos de Bogotá

**Pasto no tiene tantos avisos.** El ID de ubicación de la URL de búsqueda
(`108037152563666`) es correcto —coincide con el `city_page.id` que Facebook
geocodifica en los avisos de Pasto— pero Marketplace **no corta el scroll
infinito cuando se agota el inventario de la ciudad**: sigue rellenando con
resultados cada vez más lejanos, hasta Bogotá, a 700 km. Ningún radio explica
eso; es relleno.

Es decir que el scroll agresivo no sufre la contaminación, **la causa**: 17
listados × 80 scrolls van muchísimo más allá de donde se terminó Pasto, y todo lo
que se junta después es de otra parte.

Lo bueno es que **Facebook marca ese límite él mismo**, con un encabezado en
medio del listado:

> ### Resultados relacionados fuera de tu búsqueda

Todo lo que aparece **debajo** de ese encabezado es de otras ciudades. El scraper
lo detecta dentro de la página con `compareDocumentPosition`, así que:

1. Las tarjetas que quedaron debajo **no se recolectan**, aunque ya estén en el
   DOM del scroll actual.
2. El listado **corta el scroll ahí mismo**, después de procesar las de arriba.

Es un corte exacto, dicho por Facebook, no una heurística. En una búsqueda de
inmuebles en Pasto con filtro de 30 días, el encabezado aparece **alrededor del
décimo resultado**: ese es el inventario real de la ciudad, contra los 3440 links
que llegaba a juntar el barrido antes de este corte.

`FACEBOOK_CONSECUTIVE_OUTSIDE_LIMIT` (25 por defecto) queda como red de
seguridad, para el caso de que Facebook cambie el texto del encabezado o no lo
muestre: corta tras 25 tarjetas seguidas de otra ciudad. Un tramo corto de avisos
foráneos no corta nada —las tarjetas descartadas cuentan como avance para la
detección de estancamiento—, solo una racha larga.

En la etapa de detalle la ciudad sale de la **geocodificación que Facebook ya
hizo del aviso**, en el JSON embebido:

```json
"location":{"latitude":1.2167,"longitude":-77.2833,
  "reverse_geocode":{"city":"Pasto","city_page":{"display_name":"Pasto"}}}
```

Es el dato autoritativo y no depende del texto renderizado. De ahí salen también
`latitud`, `longitud` y `coordenadas`, que antes se guardaban **siempre en
`NULL`**: sin ellas el detector de duplicados no podía comparar por distancia
contra los otros portales.

El filtro es un *allowlist*: si la ciudad existe y no es Pasto ni un
corregimiento del catálogo, se descarta. Una lista negra de municipios deja pasar
todo lo que no nombra — así se guardaron avisos de Bogotá y Fusagasugá con
`ciudad='Pasto'`. Como último recurso, si no hay geocodificación se raspa el
rótulo "Ubicación de la vivienda" del texto; y si ese campo viene contaminado con
el texto de la página, se ignora y decide el texto libre, para no rechazar avisos
válidos. Cada descarte imprime la ciudad según Facebook, así que un rechazo
indebido se ve en el log.

> Los nombres de municipio que son también palabras corrientes se comparan con
> contexto, no sueltos: **"Bello"** es municipio de Antioquia y además el
> adjetivo de "bello apartamento". Buscarlo suelto omitía casi todos los avisos. Las imágenes salen del bloque de la publicación,
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
