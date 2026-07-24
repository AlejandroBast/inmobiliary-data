"""Deteccion centralizada de Propiedad Horizontal (PH) para los scrapers.

Amorel, Ciencuadras, FincaRaiz y Facebook Marketplace cada uno reimplementaba
su propia variante de "buscar Conjunto/Edificio/Condominio en el texto"; esto
junta esa logica en un solo lugar para que un sinonimo nuevo de un portal (o
un ajuste al detector) se enseñe una sola vez.
"""
import re
import unicodedata


def _fold(value):
    """Uppercase + sin tildes, preservando la posicion/longitud de cada caracter
    para poder recortar el nombre propio desde el texto original sin perder
    tildes ni el casing con el que el portal lo escribio."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", str(value))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").upper()


def _collapse(value):
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n-.,;:")
    return value or None


# Una negacion explicita del portal siempre gana sobre cualquier señal
# positiva (incluido un complex_name ya extraido por el scraper), para no
# contradecir el texto de origen. Se cubre "SIN <disparador>" para cada
# disparador de nombre propio (no solo PH/administracion) porque frases como
# "sin conjunto ni administracion" niegan "conjunto" antes de llegar a
# "administracion".
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

# Boundary generico para no dejar que la captura del nombre propio se coma el
# resto de la descripcion (precio, area, habitaciones, etc.).
_NAME_STOP = (
    r"(?=[.,;!?\n]|\s+(?:BARRIO|SECTOR|VALOR|PRECIO|AREA|HABITACION|HABITACIONES|"
    r"ALCOBA|ALCOBAS|BANO|BANOS|PARQUEADERO|GARAJE|PISO|PISOS|ESTRATO|CUENTA|"
    r"CONSTA|INFORMES|INF|UBICAD[OA]|VENTA|ARRIENDO|NEGOCIABLE|NEGOCIABLES)\b|$)"
)

# Nombre propio de conjunto/edificio: la señal mas especifica, se devuelve tal
# cual (con tildes/casing originales) en vez del generico "Si".
_COMPLEX_NAME_PATTERNS = [
    rf"\b(CONJUNTO(?:\s+CERRADO|\s+RESIDENCIAL|\s+CAMPESTRE)?\s+[A-Z0-9\s\-]+?){_NAME_STOP}",
    rf"\b(EDIFICIO\s+[A-Z0-9\s\-]+?){_NAME_STOP}",
    rf"\b(CONDOMINIO\s+[A-Z0-9\s\-]+?){_NAME_STOP}",
    rf"\b(URBANIZACION\s+[A-Z0-9\s\-]+?){_NAME_STOP}",
    rf"\b(UNIDAD\s+RESIDENCIAL\s+[A-Z0-9\s\-]+?){_NAME_STOP}",
    rf"\b(TORRES?\s+[A-Z0-9\s\-]+?){_NAME_STOP}",
]

# Sin nombre propio de por medio, estas menciones igual son evidencia de PH.
# "ADMINISTRACION" y "HORIZONTAL" sueltos se dejaron afuera a proposito: son
# demasiado genericos ("sin administracion", "vista horizontal") y disparaban
# falsos positivos sin un patron de negacion que los cubra en todos los casos.
_KEYWORD_PHRASES = [
    "PROPIEDAD HORIZONTAL",
    "REGIMEN DE PROPIEDAD HORIZONTAL",
    "CONJUNTO CERRADO",
    "CONJUNTO RESIDENCIAL",
    "CONJUNTO",
    "CONDOMINIO",
    "EDIFICIO",
    "UNIDAD RESIDENCIAL",
    "URBANIZACION CERRADA",
    "URBANIZACION",
    "TORRE",
    "ADMINISTRACION INCLUIDA",
    "MIRADOR TORRES",
    "RESERVAS DE",
]

# "PH"/"P H" necesita limite de palabra explicito (via regex) en vez de
# substring: pegado a puntuacion ("...en PH, cuenta...") un chequeo con
# padding de espacios se lo pierde.
_KEYWORD_REGEXES = [
    r"\bP\s*H\b",
]


def detect_ph(*texts, complex_name=None):
    """Detecta si una publicacion es Propiedad Horizontal (PH).

    Devuelve, en orden de especificidad:
      - `None` si el texto niega PH explicitamente (gana sobre todo lo demas).
      - `complex_name` si el llamador ya extrajo un nombre propio de conjunto/edificio.
      - El nombre propio encontrado en `texts` (p. ej. "Conjunto Los Rosales").
      - "Si" cuando hay evidencia de PH sin nombre propio (p. ej. "Propiedad Horizontal").
      - `None` si no hay ninguna señal de PH.
    """
    raw = "\n".join(text for text in texts if text)
    if not raw and not complex_name:
        return None

    folded = _fold(raw)

    if any(re.search(pattern, folded) for pattern in _NEGATION_PATTERNS):
        return None

    if complex_name:
        return complex_name

    for pattern in _COMPLEX_NAME_PATTERNS:
        match = re.search(pattern, folded)
        if match:
            name = _collapse(raw[match.start(1):match.end(1)])
            if name and len(name) > 2:
                return name

    if any(phrase in folded for phrase in _KEYWORD_PHRASES):
        return "Si"
    if any(re.search(pattern, folded) for pattern in _KEYWORD_REGEXES):
        return "Si"

    return None
