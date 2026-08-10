"""Deteccion centralizada de Propiedad Horizontal (PH) para los scrapers.

Amorel, Ciencuadras, FincaRaiz y Facebook Marketplace cada uno reimplementaba
su propia variante de "buscar Conjunto/Edificio/Condominio en el texto"; esto
junta esa logica en un solo lugar para que un sinonimo nuevo de un portal (o
un ajuste al detector) se enseñe una sola vez.
"""
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from inmobiliary.detectors.location import ALIASES, LEGACY_LOCATION_ALIASES, load_catalog, normalize_text


# El catalogo vive en data/ en la raiz del repo, no junto al modulo (mismo
# criterio que data/pasto_barrios_veredas.tsv en detectors/location.py).
REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "data" / "pasto_ph.tsv"

# Algunos PH del listado del cliente se llaman igual que un barrio oficial de
# Pasto ("Versalles", "El Bosque", "Gualcaloma", "Sindamanoy"...) porque el PH
# tomo el nombre del sector. Si el catalogo los usara para matching de texto,
# "apartamento en el barrio Versalles" quedaria marcado como PH "Versalles"
# aunque el aviso solo este describiendo la ubicacion, no un conjunto
# especifico. Se excluyen de catalog_match_in_text (siguen disponibles en el
# dropdown del front via ph_conjuntos, donde la eleccion es manual).
_GENERIC_NAME_STOPLIST = {"nuevo"}


@lru_cache(maxsize=1)
def _barrio_name_collisions():
    urban, rural = load_catalog()
    keys = {normalize_text(entry.canonical) for entry in list(urban.values()) + list(rural.values())}
    keys.update(normalize_text(v) for v in ALIASES.values())
    keys.update(normalize_text(v) for v in LEGACY_LOCATION_ALIASES.values())
    return keys


def _fold(value):
    """Uppercase + sin tildes, preservando la posicion/longitud de cada caracter
    para poder recortar el nombre propio desde el texto original sin perder
    tildes ni el casing con el que el portal lo escribio."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", str(value))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").upper()


# Una negacion explicita del portal siempre gana sobre cualquier señal
# positiva (incluido un nombre catalogado), para no contradecir el texto de
# origen. Se cubre "SIN <disparador>" para cada disparador de nombre propio
# (no solo PH/administracion) porque frases como "sin conjunto ni
# administracion" niegan "conjunto" antes de llegar a "administracion".
_NEGATION_PATTERNS = [
    r"\bNO\s+(?:ES\s+)?(?:UNA?\s+)?PH\b",
    r"\bSIN\s+PH\b",
    r"\bNO\s+(?:ES\s+)?PROPIEDAD\s+HORIZONTAL\b",
    r"\bSIN\s+PROPIEDAD\s+HORIZONTAL\b",
    r"\bSIN\s+CONJUNTO\b",
    r"\bSIN\s+EDIFICIO\b",
    r"\bSIN\s+CONDOMINIO\b",
    r"\bSIN\s+URBANIZACION\b",
    r"\bSIN\s+UNIDAD\s+RESIDENCIAL\b",
    r"\bSIN\s+TORRES?\b",
    r"\bSIN\s+ADMINISTRACION\b",
    r"\bADMINISTRACION\s+NO\s+INCLUIDA\b",
    r"\bNO\s+INCLUYE\s+ADMINISTRACION\b",
    r"\bNO\s+APLICA\s+ADMINISTRACION\b",
]


@lru_cache(maxsize=1)
def load_ph_catalog():
    """Catalogo de PH conocidos de Pasto: {clave_normalizada: nombre_canonico}.

    Vive en un TSV plano (un nombre por linea) en vez del formato jerarquico
    de barrios porque un PH no tiene comuna/vereda que lo contenga.
    """
    catalog = {}
    if not CATALOG_PATH.exists():
        return catalog

    for line in CATALOG_PATH.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        key = normalize_text(name)
        if key:
            catalog.setdefault(key, name)
    return catalog


def catalog_match_in_text(*texts):
    """Busca un nombre de PH del catalogo mencionado directamente en el texto.

    Muchos avisos nombran el conjunto ("Apartamento en Torres de Aquine") sin
    decir nunca "PH", "conjunto" ni "edificio", asi que la sola presencia del
    nombre catalogado ya es evidencia de PH, sin depender de esas palabras
    clave genericas.
    """
    catalog = load_ph_catalog()
    if not catalog:
        return None

    combined = normalize_text(" ".join(str(text or "") for text in texts))
    if not combined:
        return None

    excluded = _barrio_name_collisions() | _GENERIC_NAME_STOPLIST
    matches = [
        (len(key), canonical)
        for key, canonical in catalog.items()
        if key not in excluded and re.search(rf"\b{re.escape(key)}\b", combined)
    ]
    if not matches:
        return None

    _, canonical = max(matches, key=lambda item: item[0])
    return canonical


def detect_ph(*texts, complex_name=None):
    """Detecta si una publicacion es Propiedad Horizontal (PH).

    Solo devuelve un nombre cuando esta confirmado por el catalogo curado
    (data/pasto_ph.tsv / tabla ph_conjuntos): antes, si el aviso solo decia
    "conjunto cerrado" o "edificio" sin nombrar cual, o si el scraper
    extraia un nombre propio por regex ("Conjunto <lo que siga>"), ese texto
    libre se guardaba tal cual en publicaciones.ph. El filtro del front
    (getPhNombres, front/app/actions/publicaciones.ts) solo ofrece nombres
    del catalogo, asi que esos valores no gobernados quedaban invisibles ahi
    (ni aparecian bajo un PH especifico ni bajo "Sin PH"); y en avisos que
    agrupan varios inmuebles en un solo texto, el regex a veces le pegaba el
    nombre de OTRO inmueble del mismo bloque. `complex_name` (lo que haya
    extraido el scraper, p. ej. Amorel) se suma como texto de busqueda mas,
    nunca se devuelve tal cual.

    Devuelve, en orden de especificidad:
      - `None` si el texto niega PH explicitamente (gana sobre todo lo demas).
      - El nombre canonico del catalogo si el texto o `complex_name` lo mencionan.
      - `None` en cualquier otro caso (incluida evidencia generica de PH sin
        nombre catalogado: la publicacion queda sin PH en vez de "Si").
    """
    raw = "\n".join(text for text in texts if text)
    if not raw and not complex_name:
        return None

    folded = _fold(raw)

    if any(re.search(pattern, folded) for pattern in _NEGATION_PATTERNS):
        return None

    return catalog_match_in_text(*texts, complex_name)
