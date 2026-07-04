# Instalar dependencias
pip install playwright mysql-connector-python python-dotenv requests beautifulsoup4 playwright install chromium

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