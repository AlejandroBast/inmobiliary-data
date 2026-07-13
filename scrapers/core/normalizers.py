import html as html_module
import re
import unicodedata


NEGATIVE_OPERATION_PATTERNS = (
    r"\bARRIEND(?:O|A|AN|E|EN|AS|OS|AR)\b",
    r"\bARREND(?:O|A|AN|E|EN|AS|OS|AR)\b",
    r"\bALQUIL(?:O|A|AN|E|ER|ERES|AR)\b",
    r"\bRENTA\b",
    r"\bRENTO\b",
    r"\bANTICRES(?:IS|O|A)?\b",
)

SALE_PATTERNS = (
    r"\bSE\s+VENDE\b",
    r"\bEN\s+VENTA\b",
    r"\bVENTA\b",
    r"\bVENTAS\b",
    r"\bVENDO\b",
    r"\bVENDE\b",
    r"\bVENDER\b",
)

PH_PATTERNS = (
    r"\bconjunto(?:\s+(?:cerrado|residencial))?\b",
    r"\bunidad(?:\s+residencial)?\b",
    r"\bedificio\b",
    r"\bpropiedad\s+horizontal\b",
    r"\bph\b",
    r"\bcondominio\b",
    r"\btorre\b",
)

BARRIO_PATTERNS = (
    r"\bbarrio\s+([a-z0-9][a-z0-9\s.'-]{1,80}?)(?=\s+pasto\b|[,.;:$]|\s+\d+\s*m|\s+precio\b|$)",
    r"\bsector\s+([a-z0-9][a-z0-9\s.'-]{1,80}?)(?=\s+pasto\b|[,.;:$]|\s+\d+\s*m|\s+precio\b|$)",
    r"\bubicad[oa]\s+en\s+([a-z0-9][a-z0-9\s.'-]{1,80}?)(?=\s+pasto\b|[,.;:$]|\s+\d+\s*m|\s+precio\b|$)",
    r"\ben\s+([a-z0-9][a-z0-9\s.'-]{1,80}?),\s*pasto\b",
    r"\ben\s+([a-z0-9][a-z0-9\s.'-]{1,80}?)(?=\s+\$|[,.;:$]|\s+\d+\s*m|\s+precio\b|$)",
)

PROPERTY_WORDS = {
    "apartamento",
    "apartaestudio",
    "apto",
    "casa",
    "lote",
    "local",
    "oficina",
    "bodega",
    "finca",
    "venta",
    "vendo",
    "vende",
    "se",
}


def clean_text(value):
    if value is None:
        return None

    value = html_module.unescape(str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value if value else None


def normalize_text(value):
    value = clean_text(value) or ""
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.upper()


def parse_price(value):
    text = clean_text(value)
    if not text:
        return None

    normalized = normalize_text(text)

    million_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:MILLONES|MILLON|MM|M)\b", normalized)
    if million_match:
        number = float(million_match.group(1).replace(",", "."))
        return int(number * 1_000_000)

    money_match = re.search(r"\$\s*([\d][\d\.,]{4,})", text)
    if money_match:
        digits = re.sub(r"\D", "", money_match.group(1))
        return int(digits) if digits else None

    price_label_match = re.search(r"(?:PRECIO|VALOR)(?:\s+DE\s+VENTA)?\s*:?\s*\$?\s*([\d][\d\.,]{4,})", normalized)
    if price_label_match:
        digits = re.sub(r"\D", "", price_label_match.group(1))
        return int(digits) if digits else None

    numeric_candidates = re.findall(r"\b\d[\d\.,]{6,}\b", text)
    if numeric_candidates:
        digits = re.sub(r"\D", "", numeric_candidates[0])
        return int(digits) if digits else None

    return None


def parse_area(value):
    text = clean_text(value)
    if not text:
        return None

    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:m2|m²|mt2|mts2|metros)", text, flags=re.IGNORECASE)
    if not match:
        return None

    number = match.group(1)
    if "," in number and "." in number:
        number = number.replace(".", "").replace(",", ".")
    else:
        number = number.replace(",", ".")

    try:
        return float(number)
    except ValueError:
        return None


def sale_status(value):
    normalized = normalize_text(value)

    for pattern in NEGATIVE_OPERATION_PATTERNS:
        if re.search(pattern, normalized):
            return False, "no_venta"

    for pattern in SALE_PATTERNS:
        if re.search(pattern, normalized):
            return True, "venta"

    return False, "sin_palabra_venta"


def is_sale_listing(value):
    return sale_status(value)[0]


def _clean_barrio_candidate(value):
    value = clean_text(value)
    if not value:
        return None

    value = re.sub(r"\b(pasto|narino|nariño)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(precio|valor|area|área)\b.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+\d+.*$", "", value)
    value = value.strip(" ,.;:-")
    value = clean_text(value)

    if not value:
        return None

    words = value.lower().split()
    while words and words[0] in PROPERTY_WORDS:
        words.pop(0)

    value = " ".join(words).strip(" ,.;:-")
    if not value or value.lower() in PROPERTY_WORDS:
        return None

    return value.title()


def extract_barrio(value):
    text = clean_text(value)
    if not text:
        return None

    for pattern in BARRIO_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            barrio = _clean_barrio_candidate(match.group(1))
            if barrio:
                return barrio

    return None


def detect_ph(value):
    text = clean_text(value)
    if not text:
        return None

    for pattern in PH_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(0)).title()

    return None


def calculate_precio_m2(precio, m2):
    try:
        precio_value = float(precio)
        m2_value = float(m2)
    except (TypeError, ValueError):
        return None

    if precio_value <= 0 or m2_value <= 0:
        return None

    return precio_value / m2_value
