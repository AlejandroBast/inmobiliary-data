# Deteccion de publicaciones del mismo inmueble

El detector conserva todas las publicaciones. Las dos senales principales para
asociar dos avisos son **las imagenes y el precio**; el resto de los campos
(direccion, area, habitaciones, banos, estrato...) corrobora o contradice.

### El precio

| Diferencia | Senal | Puntos |
|---|---|---|
| exacta | `same_price` | +12 |
| <= 5% | `very_similar_price` | +8 |
| <= 15% | `similar_price` | +3 |
| >= `DUPLICATE_PRICE_MAX_DIFFERENCE` (30%) | `different_price` | **-25** |

El mismo inmueble reSubido conserva el precio o lo mueve poco. Antes el precio
solo sumaba 3 puntos al 15% y **nunca restaba**, asi que dos inmuebles con
precios muy distintos quedaban emparejados si compartian una foto: un mismo
vendedor suele reusar fotos del edificio entre unidades diferentes.

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
DUPLICATE_PERCEPTUAL_MAX_DISTANCE=6
DUPLICATE_PRICE_MAX_DIFFERENCE=0.30
```

## Lo revisado a mano nunca se pierde

`backfill_duplicate_detection.py --rebuild` borra solo las coincidencias en
estado `pendiente` y los grupos `automatico`. Las **confirmadas** y las
**descartadas** se conservan, y volver a correr el detector no las devuelve al
estado automatico.

Una coincidencia solo se agrupa automaticamente cuando supera el umbral de 80
y contiene dos imagenes identicas, o una imagen junto a una direccion exacta o
coordenadas a 30 metros. Ademas exige area compatible, o habitaciones y banos
coincidentes cuando existan. Las coordenadas solas quedan por debajo
del umbral de revision para evitar unir apartamentos diferentes de un edificio.

Dos fotos cuentan como coincidencia de dos maneras:

- **SHA-256 identico**: el mismo archivo byte a byte. Vale hasta 50 puntos.
- **dHash a distancia <= `DUPLICATE_PERCEPTUAL_MAX_DISTANCE` (6)**: la misma foto
  reSubida. Vale hasta 45.

El criterio de solo-SHA-256 dejaba pasar duplicados reales: Facebook recomprime
la foto al reSubirla y el hash exacto cambia por completo. Sobre datos reales la
separacion es tajante, sin zona gris: los pares del mismo inmueble dieron
distancia 0 y todos los demas 16 o mas.

Ninguna de las dos senales alcanza sola el umbral de revision (60), y es
deliberado: dos avisos distintos pueden compartir una foto generica. Siempre
hace falta corroboracion de otro campo.

### La direccion tiene que ser de calle

Varios scrapers arman `direccion` como `"<barrio>, <ciudad>, <departamento>"`,
asi que dos inmuebles distintos del mismo barrio traen la misma cadena. Esa
coincidencia ya no suma: solo puntua una direccion con nivel de calle (`kr 5`,
`cl 20`, `mz 3`). Si no lo tiene, queda anotada como `same_area_not_address` con
0 puntos, para que la auditoria muestre que se evaluo. Sin esto sumaba 20 puntos
que repetian lo que ya cubren `same_neighborhood` y `same_city`.

### Coordenadas aproximadas

Facebook publica coordenadas, pero son de una grilla a nivel ciudad: en una
corrida real **51 de 60 avisos compartieron la misma coordenada exacta**. Por eso
su scraper no las guarda en `latitud`/`longitud` —quedan en `links_adicionales`
como referencia—: el detector veia distancia 0 m entre inmuebles sin relacion y
sumaba 30 puntos a cada par.

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
