# Deteccion de publicaciones del mismo inmueble

El detector conserva todas las publicaciones. Compara hashes perceptuales de
imagenes, coordenadas, direccion, area, habitaciones y banos. El precio no
reduce el puntaje, por lo que un inmueble puede aparecer con valores distintos.

## Preparacion

Desde `inmobiliary-data`:

```powershell
python -m pip install Pillow
python apply_duplicate_migration.py
```

La migracion inversa esta en `migrations/001_duplicate_detection_down.sql`.
Aplicarla elimina solamente los resultados del detector, nunca las
publicaciones ni sus evidencias.

## Configuracion opcional

```dotenv
DUPLICATE_DETECTION_ENABLED=true
DUPLICATE_AUTO_THRESHOLD=80
DUPLICATE_REVIEW_THRESHOLD=60
DUPLICATE_MAX_DISTANCE_METERS=100
DUPLICATE_MIN_IMAGE_WIDTH=200
DUPLICATE_MIN_IMAGE_HEIGHT=150
DUPLICATE_BACKFILL_BATCH_SIZE=100
```

Una coincidencia solo se agrupa automaticamente cuando supera el umbral de 80
y contiene dos imagenes identicas, o una imagen junto a una direccion exacta o
coordenadas a 30 metros. Ademas exige area compatible, o habitaciones y banos
coincidentes cuando existan. Las coordenadas solas quedan por debajo
del umbral de revision para evitar unir apartamentos diferentes de un edificio.

Dos fotos solo cuentan como coincidencia cuando el SHA-256 de sus archivos es
exactamente igual. El dHash se conserva como dato perceptual de diagnostico,
pero ya no decide si dos imagenes coinciden.

La migracion `002_exact_image_hash.sql` se aplica mediante
`python apply_duplicate_migration.py`. La columna comienza nullable y el
backfill completa los SHA-256 historicos sin modificar las imagenes.

Metrocuadrado ejecuta el detector despues de guardar todas sus imagenes. Para
analizar las publicaciones e imagenes existentes:

```powershell
python backfill_duplicate_detection.py
```

El proceso es incremental: los hashes ya almacenados no se vuelven a calcular.
Si el detector falla, la insercion del scraper se conserva y se imprime una
advertencia.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```
