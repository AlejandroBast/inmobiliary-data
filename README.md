# inmobiliary-data

Sistema interno mono-usuario para capturar y revisar comparables inmobiliarios en venta en Pasto, Narino. Incluye scrapers Python, base MySQL y frontend Next.js.

## Requisitos

- Node.js 20+ y npm
- Python 3.11+
- MySQL 8+
- Playwright Chromium

## Configurar variables

La clave real no debe subirse al repo. El archivo `.env.local` esta ignorado por git.

```powershell
Copy-Item .env.local.example .env.local
notepad .env.local
```

Completa:

```dotenv
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=TU_CLAVE_REAL
DB_NAME=db_inmobiliary_data
```

Para el frontend, copia los mismos valores en `front/.env.local`:

```powershell
Copy-Item .env.local front/.env.local
```

## Crear la base de datos

`inmobiliary_db.sql` borra y crea la base desde cero de forma intencional.

```powershell
cmd /c "mysql -h localhost -P 3306 -u root -p < inmobiliary_db.sql"
```

## Instalar Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Ejecutar frontend

```powershell
cd front
npm install
npm run dev
```

El frontend corre en `http://localhost:3001`.

Para build de produccion:

```powershell
cd front
npm run build
```

## Ejecutar scrapers

Todos se ejecutan desde la raiz del repo y mantienen su comando original:

```powershell
python scraper_fincaraiz_pasto.py
python scraper_ciencuadras.py
python scraper_metrocuadrado_pasto.py
python scraper_amorel_pasto.py
python scraper_facebook_marketplace.py
```

Facebook usa un perfil local en `.facebook_profile/`. En el primer uso puede pedir login o captcha.

Prueba Facebook sin guardar:

```powershell
$env:FACEBOOK_DRY_RUN="true"
$env:FACEBOOK_MAX_DETAILS="5"
python scraper_facebook_marketplace.py
```

## Notas de operacion

- El sistema guarda solo inmuebles en venta.
- Arriendo, alquiler, renta y anticresis se descartan.
- Precio mayor a cero y barrio identificable son obligatorios para guardar.
- Las evidencias HTML, screenshots e imagenes quedan en `evidencias/`.
- Auditorias y logs quedan en `logs/`.
- `.env.local`, `front/.env.local`, `node_modules/`, `.next/`, caches Python y evidencias locales no se suben al repo.

## Pruebas

```powershell
python -m pytest
```

Las pruebas cubren normalizacion de precio, venta vs arriendo/anticresis, extraccion de barrio, deteccion de PH/conjunto, area y precio por metro cuadrado.
