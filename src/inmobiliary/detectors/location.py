import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


# El catalogo vive en data/ en la raiz del repo, no junto al modulo.
REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "data" / "pasto_barrios_veredas.tsv"
OUTSIDE_PLACES = {
    "bogota", "bello", "buesaco", "chachagui", "cundinamarca", "girardot",
    "imues", "medellin", "mocoa", "ricaurte", "sandona", "taminango",
}
NOISE_WORDS = re.compile(
    r"\b(?:publicidad|precio|negociable|info(?:rmes?)?|cuenta\s+con|consta\s+de|"
    r"area|valor|contacto|whatsapp|mts?2?|metros?|frente|fondo)\b.*$",
    re.IGNORECASE,
)
PH_PREFIX = re.compile(
    r"^\s*(?:conjunto|condominio|edificio|edif\.?|torres?|unidad\s+residencial)\b",
    re.IGNORECASE,
)
REFERENCE_PREFIX = re.compile(r"\b(?:cerca\s+de|a\s+pocos|minutos\s+de|via\s+a|frente\s+a|antes\s+de)\b", re.IGNORECASE)
ALIASES = {
    "avenida de los estudiantes": "Avenida Los Estudiantes",
    "luna 1": "Las lunas I",
    "obrero": "San José Obrero",
    "toro bajo": "Torobajo",
    "villa flor 2": "Villaflor II",
    "violetas 2": "Las Violetas II",
}

# Ultimo recurso para nombres usados tradicionalmente por los anunciantes que
# no aparecen como barrio independiente en el catalogo oficial. Se mantienen
# acotados para no convertir cualquier conjunto o punto de referencia en barrio.
LEGACY_LOCATION_ALIASES = {
    "torres de iguazu": "Torres de Iguazú",
    "mirador torres de aquine": "Aquine",
    "mirador de aquine": "Aquine",
    "unicentro": "Unicentro",
}
TEXT_SCAN_EXCLUSIONS = {"parque infantil"}


def normalize_text(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn").lower()
    text = re.sub(r"\bxxiii\b", "23", text)
    text = re.sub(r"\biv\b", "4", text)
    text = re.sub(r"\biii\b", "3", text)
    text = re.sub(r"\bii\b", "2", text)
    text = re.sub(r"\bi\b", "1", text)
    text = re.sub(r"\b(?:et|etapa)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean_location_text(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,.-")
    text = re.sub(r"^(?:barrio|vereda|corregimiento)(?:\s+de)?\s+", "", text, flags=re.IGNORECASE)
    text = NOISE_WORDS.sub("", text).strip(" ,.-")
    return text or None


@dataclass(frozen=True)
class CatalogEntry:
    canonical: str
    kind: str
    parent: str | None = None


@dataclass
class LocationResult:
    value: str | None
    kind: str = "desconocido"
    confidence: int = 0
    reason: str = "sin coincidencia"
    original: str | None = None
    suggestions: list[str] = field(default_factory=list)
    outside_municipality: str | None = None

    @property
    def accepted(self):
        return self.value is not None and self.confidence >= 80 and not self.outside_municipality


@lru_cache(maxsize=1)
def load_catalog():
    urban = {}
    rural = {}
    for line in CATALOG_PATH.read_text(encoding="utf-8").splitlines():
        parts = [part.strip() for part in line.split("\t") if part.strip()]
        if len(parts) >= 4 and parts[0] == "Comuna:" and parts[2] == "Barrio:":
            name = " ".join(parts[3:]).strip()
            urban.setdefault(normalize_text(name), CatalogEntry(name, "barrio", parts[1]))
        elif len(parts) >= 4 and parts[0] == "Corregimiento:" and parts[2] == "Vereda:":
            name = parts[1]
            rural.setdefault(normalize_text(name), CatalogEntry(name, "corregimiento"))
    return urban, rural


def detect_outside_municipality(*texts):
    city = normalize_text(texts[0] if texts else None)
    combined = normalize_text(" ".join(str(text or "") for text in texts[1:]))
    for place in OUTSIDE_PLACES:
        if city == place:
            return place.title()
        strong_context = rf"\b(?:municipio\s+de|ciudad\s+de|ubicad[oa]\s+en|casa\s+en|apartamento\s+en|lote\s+en|en)\s+(?:el\s+|la\s+)?{re.escape(place)}\b"
        if re.search(strong_context, combined) or place == "cundinamarca" and re.search(r"\bcundinamarca\b", combined):
            return place.title()
    return None


def catalog_match(value, allow_contained=True):
    urban, rural = load_catalog()
    clean = clean_location_text(value)
    key = normalize_text(clean)
    if not key:
        return None

    alias = ALIASES.get(key)
    if alias:
        alias_entry = urban.get(normalize_text(alias))
        if alias_entry:
            return alias_entry, 95, "alias controlado"

    if key in urban:
        return urban[key], 100, "barrio oficial exacto"
    if key in rural:
        return rural[key], 100, "corregimiento oficial exacto"

    if allow_contained:
        matches = [(len(name), entry) for name, entry in urban.items() if re.search(rf"\b{re.escape(name)}\b", key)]
        if matches:
            _, entry = max(matches, key=lambda item: item[0])
            return entry, 90, "barrio oficial dentro del texto de ubicacion"
    return None


def catalog_match_in_text(*texts):
    """Busca nombres oficiales escritos directamente en titulo/descripcion."""
    urban, rural = load_catalog()
    combined = normalize_text(" ".join(str(text or "") for text in texts))
    if not combined:
        return None

    matches = [
        (len(key), entry)
        for key, entry in {**urban, **rural}.items()
        if key not in TEXT_SCAN_EXCLUSIONS
        and re.search(rf"\b{re.escape(key)}\b", combined)
    ]
    if not matches:
        return None
    _, entry = max(matches, key=lambda item: item[0])
    return entry, 85, "nombre oficial mencionado directamente en el texto"


def legacy_location_match(*texts):
    combined = normalize_text(" ".join(str(text or "") for text in texts))
    matches = [
        (len(alias), canonical)
        for alias, canonical in LEGACY_LOCATION_ALIASES.items()
        if re.search(rf"\b{re.escape(alias)}\b", combined)
    ]
    if not matches:
        return None
    _, canonical = max(matches, key=lambda item: item[0])
    return LocationResult(
        canonical,
        "ubicacion tradicional",
        80,
        "alias tradicional aplicado despues de agotar el catalogo oficial",
    )


def explicit_description_candidates(text):
    candidates = []
    patterns = [
        r"\b(?:barrio|urbanizacion|urb\.?|sector)\s+(?:(?:de|del)\s+)?(?:el\s+|la\s+)?([^\n,.;:\-]{2,80})",
        r"\bcorregimiento\s+(?:(?:de|del)\s+)?(?:el\s+|la\s+)?([^\n,.;:\-]{2,80})",
        r"\bubicad[oa]\s+en\s+(?:(?:de|del)\s+)?(?:el\s+|la\s+)?([^\n,.;:\-]{2,80})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, str(text or ""), re.IGNORECASE):
            fragment = clean_location_text(match.group(1))
            if fragment and not REFERENCE_PREFIX.search(fragment):
                candidates.append(fragment)
    return candidates


def suggestions_for(value, limit=4):
    urban, rural = load_catalog()
    names = {**urban, **rural}
    key = normalize_text(clean_location_text(value))
    close = difflib.get_close_matches(key, names.keys(), n=limit, cutoff=0.62)
    return [names[item].canonical for item in close]


def resolve_pasto_location(candidate=None, *, title=None, description=None, address=None, city=None, ph=None):
    original = clean_location_text(candidate)
    outside = detect_outside_municipality(city, address, title, description)
    if outside and normalize_text(outside) != "pasto":
        return LocationResult(None, "otro municipio", 100, "municipio externo mencionado explicitamente", original, outside_municipality=outside)

    if original and PH_PREFIX.search(original):
        direct = None
    else:
        direct = catalog_match(original)
    if direct:
        entry, confidence, reason = direct
        return LocationResult(entry.canonical, entry.kind, confidence, reason, original)

    for text in (title, address, description):
        for fragment in explicit_description_candidates(text):
            match = catalog_match(fragment)
            if match:
                entry, confidence, reason = match
                return LocationResult(entry.canonical, entry.kind, min(confidence, 90), f"{reason}; frase explicita", original)

    direct_text_match = catalog_match_in_text(title, address, description)
    if direct_text_match:
        entry, confidence, reason = direct_text_match
        return LocationResult(entry.canonical, entry.kind, confidence, reason, original)

    legacy = legacy_location_match(original, title, address, description)
    if legacy:
        legacy.original = original
        return legacy

    reason = "propiedad horizontal en campo barrio" if original and PH_PREFIX.search(original) else "ubicacion no reconocida"
    return LocationResult(None, "propiedad horizontal" if "horizontal" in reason else "desconocido", 0, reason, original, suggestions_for(original))


def location_diagnostic(result):
    if result.outside_municipality:
        return f"fuera_de_pasto={result.outside_municipality}; original={result.original!r}"
    if result.accepted:
        return f"normalizada={result.value!r}; tipo={result.kind}; confianza={result.confidence}; razon={result.reason}"
    options = ", ".join(result.suggestions) or "sin opciones"
    return f"sin_barrio_seguro; original={result.original!r}; razon={result.reason}; opciones={options}"
