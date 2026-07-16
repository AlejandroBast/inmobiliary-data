import hashlib
import html as html_module
import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

try:
    import mysql.connector
    from mysql.connector import IntegrityError
except ImportError:
    mysql = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None

from duplicate_detector import detect_duplicates_safely
from location_normalizer import location_diagnostic, resolve_pasto_location
from scraper_audit import ScraperAudit


load_dotenv()

# URL base del listado de Finca Raiz (mezclado). Se usa solo como raiz para
# construir las URLs de las subcategorias de VENTA (ver SALE_SUBCATEGORIES).
SEARCH_URL = os.getenv(
    "AMOREL_SEARCH_URL",
    "https://amorelpasto.com/clasificados/web/app.php/resultados/Finca%20Raiz",
)
BASE_URL = "https://amorelpasto.com"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "boludo123"),
    "database": os.getenv("DB_NAME", "db_inmobiliary_data"),
}

# 0 = todas las paginas detectadas por subcategoria.
MAX_PAGES = int(os.getenv("AMOREL_MAX_PAGES", "0"))
REQUEST_PAUSE_SECONDS = float(os.getenv("REQUEST_PAUSE_SECONDS", "0.5"))
PAGE_PAUSE_SECONDS = float(os.getenv("AMOREL_PAGE_PAUSE_SECONDS", "0.3"))
IMAGE_DOWNLOAD_WORKERS = int(os.getenv("IMAGE_DOWNLOAD_WORKERS", "6"))
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "12"))
MIN_SALE_PRICE = int(os.getenv("AMOREL_MIN_SALE_PRICE", "10000000"))

EVIDENCE_DIR = Path("evidencias")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Subcategorias de VENTA reales del sitio (menu lateral "Sub Categorias").
# Entrar directo por aqui es el filtro mas fuerte posible: es el propio sitio
# el que ya separo arriendo / anticresis / venta, en vez de adivinar por texto.
# El segundo valor es el tipo de inmueble que esa subcategoria garantiza
# (None cuando la subcategoria mezcla varios tipos, ej. locales/oficinas/bodegas).
# ---------------------------------------------------------------------------
SALE_SUBCATEGORIES = [
    ("apartamentos ventas", "Apartamento"),
    ("casas venta", "Casa"),
    ("fincas venta", "Finca"),
    ("lotes venta", "Lote"),
    ("locales, oficinas y bodegas en venta", None),
]

NEGATIVE_TITLE_KEYWORDS = [
    "ARRIENDO",
    "ARRIENDA",
    "ARRIENDAS",
    "ARRENDO",
    "ARRENDA",
    "ARRENDAR",
    "ARRENDAMOS",
    "ARRENDANDO",
    "RENTA",
    "RENTO",
    "RENTAR",
    "ALQUILA",
    "ALQUILO",
    "ALQUILER",
    "ALQUILAR",
    "ANTICRES",
    "ANTICRESA",
    "ANTICRESO",
    "ANTICRESIS",
    "ANTICRETICO",
    "PERMUTO",
    "PERMUTA",
    "PERMUTAR",
    "CAMBIO POR",
    "INTERCAMBIO",
    "COMPRO",
    "COMPRA DE",
    "SE COMPRA",
    "CEDO",
    "CEDE",
    "CESION",
    "BUSCO",
    "BUSCA",
    "BUSQUEDA",
    "SE BUSCA",
]

SALE_KEYWORDS = ["VENTA", "VENTAS", "VENDE", "VENDO", "VENDER"]

PROPERTY_TYPES = [
    ("Apartaestudio", ["APARTAESTUDIO", "APARTA ESTUDIO"]),
    ("Apartamento", ["APARTAMENTO", "APARTAMENTOS", "APTO"]),
    ("Casa", ["CASA", "CASAS"]),
    ("Oficina", ["OFICINA", "OFICINAS"]),
    ("Local", ["LOCAL", "LOCALES"]),
    ("Bodega", ["BODEGA", "BODEGAS"]),
    ("Lote", ["LOTE", "LOTES", "TERRENO"]),
    ("Finca", ["FINCA", "FINCAS"]),
    ("Habitacion", ["HABITACION", "HABITACIONES", "ALCOBA"]),
]


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
    # "86 M²" -> "86 M2". El superindice no es una tilde (no se quita con NFD),
    # asi que sin esto extract_area/extract_price pierden datos de forma silenciosa.
    value = value.replace("\u00b2", "2").replace("\u00b3", "3")
    return value.upper()


def safe_url(url):
    parts = urlsplit(url)
    path = quote(unquote(parts.path), safe="/%")
    query = quote(unquote(parts.query), safe="=&%")
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def fetch_url(url, timeout=45):
    request = Request(safe_url(url), headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        content = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        final_url = response.geturl()
    text = content.decode(charset, "replace")
    if "\ufffd" in text:
        fallback = content.decode("cp1252", "replace")
        if fallback.count("\ufffd") < text.count("\ufffd"):
            text = fallback
    return text, final_url


class SimpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.images = []
        self.text_parts = []
        self._link_href = None
        self._link_text = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return

        if tag == "a" and attrs.get("href"):
            self._link_href = attrs["href"]
            self._link_text = []

        if tag == "img":
            self.images.append(attrs)

        if tag in {"br", "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "tr"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if tag == "a" and self._link_href is not None:
            self.links.append((clean_text(" ".join(self._link_text)) or "", self._link_href))
            self._link_href = None
            self._link_text = []

        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "tr"}:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._link_href is not None:
            self._link_text.append(data)
        if data.strip():
            self.text_parts.append(data.strip())

    def text(self):
        raw = " ".join(self.text_parts)
        raw = re.sub(r"\s*\n\s*", "\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        return raw.strip()


def parse_html(html):
    parser = SimpleHTMLParser()
    parser.feed(html)
    return parser


def get_lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


PUBLICATION_LINK_PATTERN = re.compile(
    r"/(?:publicacion|publicaciones|anuncio)/(\d+)(?:[/?#-]|$)",
    re.IGNORECASE,
)


def canonicalize_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), parts.query, ""))


def is_amorel_url(url):
    return urlsplit(url).netloc.lower().endswith(urlsplit(BASE_URL).netloc.lower())


def extract_publication_id(url):
    # Evita confundir las URLs de imagen /api/v1/anuncio/{id}/imagen con publicaciones.
    if "/api/v1/anuncio/" in url:
        return None
    match = PUBLICATION_LINK_PATTERN.search(url)
    return match.group(1) if match else None


def is_publication_url(url):
    return extract_publication_id(url) is not None


def build_subcategory_url(subcat_label):
    """
    Construye la URL de una subcategoria de venta a partir de SEARCH_URL.
    safe_url() se encarga de normalizar espacios/comas al hacer la peticion,
    asi que aqui se puede concatenar el nombre "en crudo".
    """
    base = SEARCH_URL.rstrip("/")
    return f"{base}/{subcat_label}"


def build_page_url(base_url, page_number):
    if page_number <= 1:
        return base_url

    parts = urlsplit(base_url)
    query = parts.query
    if re.search(r"(^|&)pagina=\d+", query):
        query = re.sub(r"(^|&)pagina=\d+", rf"\1pagina={page_number}", query)
    else:
        query = f"{query}&pagina={page_number}" if query else f"pagina={page_number}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def collect_publication_links():
    """
    Recorre unicamente las subcategorias de VENTA reales del sitio
    (SALE_SUBCATEGORIES). Por cada una hace paginacion secuencial ?pagina=N
    hasta que dos paginas seguidas no traen links nuevos.

    A diferencia de la version anterior, NO sigue enlaces de navegacion
    encontrados dentro del HTML (el sidebar de cada pagina trae links a
    TODAS las categorias, incluyendo arriendo/anticresis, y seguirlos
    rompe el filtro "solo ventas" ademas de desperdiciar peticiones).

    Devuelve: lista de (url_publicacion, tipo_inmueble_sugerido_por_subcategoria)
    """
    audit = ScraperAudit("Amorel", SEARCH_URL)
    all_links = []  # lista de (url, tipo_inmueble_hint)
    seen_publications = set()
    total_pages_scanned = 0
    page_sequence = 0

    for subcat_label, tipo_hint in SALE_SUBCATEGORIES:
        subcat_base_url = canonicalize_url(build_subcategory_url(subcat_label))
        print(f"[INFO] === Subcategoria de venta: '{subcat_label}' -> {subcat_base_url}")

        empty_streak = 0
        page_number = 1
        pages_scanned_subcat = 0

        while True:
            if MAX_PAGES > 0 and pages_scanned_subcat >= MAX_PAGES:
                break

            page_url = canonicalize_url(build_page_url(subcat_base_url, page_number))
            page_sequence += 1

            try:
                html, final_url = fetch_url(page_url)
                final_url = canonicalize_url(final_url)
            except Exception as error:
                reason = f"No se pudo abrir la pagina {page_url}: {error}"
                print(f"[WARN] {reason}")
                audit.record_page(page_sequence, url=page_url, status="error", reason=reason)
                empty_streak += 1
                page_number += 1
                pages_scanned_subcat += 1
                total_pages_scanned += 1
                if empty_streak >= 2:
                    break
                continue

            parser = parse_html(html)
            page_seen = set()
            page_links_count = 0
            new_links_count = 0
            duplicate_links_count = 0

            for _link_text, href in parser.links:
                full_url = canonicalize_url(urljoin(final_url, href))
                if not is_publication_url(full_url):
                    continue

                publicacion_id = extract_publication_id(full_url)
                if not publicacion_id or publicacion_id in page_seen:
                    continue
                page_seen.add(publicacion_id)
                page_links_count += 1

                if publicacion_id in seen_publications:
                    duplicate_links_count += 1
                else:
                    seen_publications.add(publicacion_id)
                    all_links.append((full_url, tipo_hint))
                    new_links_count += 1

            audit.record_page(
                page_sequence,
                url=page_url,
                links_count=page_links_count,
                new_links_count=new_links_count,
                duplicate_links_count=duplicate_links_count,
                status="ok",
                reason=f"venta:{subcat_label}",
            )
            print(
                f"[INFO] [{subcat_label}] Pagina {page_number}: {page_links_count} links, "
                f"{new_links_count} nuevos, {duplicate_links_count} repetidos | {page_url}"
            )

            pages_scanned_subcat += 1
            total_pages_scanned += 1

            if page_links_count == 0 or new_links_count == 0:
                empty_streak += 1
            else:
                empty_streak = 0

            if empty_streak >= 2:
                break

            page_number += 1
            if PAGE_PAUSE_SECONDS > 0:
                time.sleep(PAGE_PAUSE_SECONDS)

    limit_reason = None
    if MAX_PAGES > 0:
        limit_reason = f"AMOREL_MAX_PAGES={MAX_PAGES}; el recorrido se detuvo al llegar a ese limite (por subcategoria)."

    audit.set_listing_summary(
        total_reported=None,
        pages_expected=None,
        pages_planned=total_pages_scanned,
        page_size=None,
        limit_reason=limit_reason,
    )

    print(f"[INFO] Paginas Amorel revisadas (solo subcategorias de venta): {total_pages_scanned}")
    print(f"[INFO] Publicaciones de venta encontradas: {len(all_links)}")
    return all_links, audit


def parse_money_digits(raw):
    digits = re.sub(r"[^\d]", "", raw or "")
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def extract_price(text):
    """
    Amorel a veces muestra $0 en la tarjeta, pero el valor real aparece en
    "DETALLES DE LA PUBLICACION" como VALOR $ 165.000.000.
    Por eso SIEMPRE se calcula desde el detalle completo, no desde la tarjeta.
    """
    candidates = []
    source = text or ""
    source_norm = normalize_text(source)

    contextual_patterns = [
        r"(?:VALOR|PRECIO|VENTA|SE\s+VENDE\s+EN|SE\s+PIDE|INVERSION)\s*(?:DE|EN|COP)?\s*\$?\s*([\d][\d\s\.,']{4,})",
        r"\$\s*([\d][\d\s\.,']{4,})",
    ]

    for pattern in contextual_patterns:
        for match in re.finditer(pattern, source_norm):
            value = parse_money_digits(match.group(1))
            if value and value >= MIN_SALE_PRICE:
                candidates.append(value)

    million_pattern = r"(\d+(?:[\.,]\d+)?)\s*(?:MILLONES|MILLON|MILL)"
    for match in re.finditer(million_pattern, source_norm):
        number = match.group(1).replace(",", ".")
        try:
            value = int(float(number) * 1_000_000)
        except ValueError:
            continue
        if value >= MIN_SALE_PRICE:
            candidates.append(value)

    return max(candidates) if candidates else None


def is_price_negotiable(text):
    return bool(re.search(r"\bNEGOCIABLE\b", normalize_text(text)))


def is_sale_listing(title, category, description):
    """
    Determina si una publicacion es realmente una VENTA (no arriendo, no
    anticresis, no permuta, no compra, no cesion).

    Estrategia en capas:
    1. La categoria propia del sitio (ej. "Apartamentos Ventas") es la senal
       mas confiable porque viene de como el publicador clasifico el aviso.
       Si la categoria menciona arriendo/anticresis explicitamente, se
       rechaza de una vez.
    2. Aun si la categoria dice "venta", se revisa titulo + descripcion +
       categoria en busca de palabras negativas (arriendo, permuta, cesion,
       compra, etc.) porque hay avisos mixtos tipo
       "VENDO, ARRIENDO O PERMUTO" que no son una venta pura.
    3. Si no hay categoria disponible (fallback), se exige encontrar una
       palabra de venta en titulo o descripcion.
    """
    title_norm = normalize_text(title or "")
    category_norm = normalize_text(category or "")
    description_norm = normalize_text(description or "")
    combined = f"{title_norm} {category_norm} {description_norm}"

    if category_norm and any(
        keyword in category_norm
        for keyword in ["ARRIENDO", "ANTICRES", "ANTICRESIS", "ANTICRETICO"]
    ):
        return False, "categoria_no_es_venta"

    if any(keyword in combined for keyword in NEGATIVE_TITLE_KEYWORDS):
        return False, "oferta_mixta_no_es_venta_pura"

    if category_norm and "VENTA" in category_norm:
        return True, None

    if any(keyword in title_norm for keyword in SALE_KEYWORDS):
        return True, None

    if any(keyword in description_norm for keyword in SALE_KEYWORDS):
        return True, None

    return False, "sin_palabra_venta"


def extract_codigo(text, url):
    match = re.search(r"\bFSE\s*(\d+(?:-\d+)?)\b", text or "", re.IGNORECASE)
    if match:
        return f"FSE {match.group(1)}"
    publicacion_id = extract_publication_id(url)
    return f"AMOREL {publicacion_id}" if publicacion_id else None


def extract_header(lines):
    for index, line in enumerate(lines):
        match = re.search(r"(.+?)\s+FSE\s+\d+\s*$", line, re.IGNORECASE)
        if not match:
            continue

        title = clean_text(match.group(1))
        date = None
        category = None
        if index + 1 < len(lines):
            date_category = re.search(r"(\d{4}-\d{2}-\d{2})\s*-\s*(.+)", lines[index + 1])
            if date_category:
                date = date_category.group(1)
                category = clean_text(date_category.group(2))

        return title, date, category

    codigo_index = None
    for index, line in enumerate(lines):
        if re.fullmatch(r"FSE\s+\d+", line, re.IGNORECASE):
            codigo_index = index
            break

    title = None
    date = None
    category = None

    if codigo_index is not None:
        for index in range(codigo_index - 1, -1, -1):
            candidate = clean_text(lines[index])
            normalized = normalize_text(candidate)
            if candidate and not normalized.startswith(("INICIO", "AMOREL", "NAVEGACION", "DETALLES")):
                title = candidate
                break

        for index in range(codigo_index + 1, min(codigo_index + 8, len(lines))):
            date_category = re.search(r"(\d{4}-\d{2}-\d{2})\s*-\s*(.+)", lines[index])
            if date_category:
                date = date_category.group(1)
                category = clean_text(date_category.group(2))
                break
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", lines[index]):
                date = lines[index]
            elif lines[index] != "-" and re.search(r"\b(Venta|Ventas|Arriendo|Anticres)\b", lines[index], re.IGNORECASE):
                category = lines[index]
                break

    return title, date, category


def extract_description(lines):
    start = None
    for index, line in enumerate(lines):
        normalized = normalize_text(line)
        if "DETALLES DE LA PUBLICACI" in normalized or "DETALLES DE LA PUBLICACION" in normalized:
            start = index + 1
            break

    if start is None:
        return None

    stop_markers = [
        "CONTACTE AL VENDEDOR",
        "CONSEJOS PARA",
        "INICIO",
        "NUESTRAS NOVEDADES",
    ]
    values = []
    for line in lines[start:]:
        normalized = normalize_text(line)
        if any(marker in normalized for marker in stop_markers):
            break
        if re.fullmatch(r"\d{7,12}", line):
            continue
        values.append(line)

    return clean_text("\n".join(values))


def extract_property_type(title, category, description, tipo_hint=None):
    # La subcategoria de origen (Casa/Apartamento/Finca/Lote) es la fuente
    # mas confiable porque la garantiza el propio sitio. Solo se recurre a
    # las palabras clave del texto cuando la subcategoria es mixta
    # (locales/oficinas/bodegas) o no vino ningun hint.
    if tipo_hint:
        return tipo_hint

    source = normalize_text(f"{title or ''} {category or ''} {description or ''}")
    for label, keywords in PROPERTY_TYPES:
        if any(keyword in source for keyword in keywords):
            return label
    return None


SPANISH_SMALL_NUMBERS = {
    "UN": 1,
    "UNA": 1,
    "UNO": 1,
    "DOS": 2,
    "TRES": 3,
    "CUATRO": 4,
    "CINCO": 5,
    "SEIS": 6,
    "SIETE": 7,
    "OCHO": 8,
    "NUEVE": 9,
    "DIEZ": 10,
}


def parse_small_int(value):
    if value is None:
        return None
    value_norm = normalize_text(str(value)).strip()
    if value_norm.isdigit():
        return int(value_norm)
    return SPANISH_SMALL_NUMBERS.get(value_norm)


def smart_title(value):
    value = clean_text(value)
    if not value:
        return None

    keep_upper = {"PH", "VIP", "VIS"}
    words = []
    for word in value.lower().split():
        raw = word.strip("-_,.;:")
        if not raw:
            continue
        if raw.upper() in keep_upper:
            words.append(raw.upper())
        else:
            words.append(raw.capitalize())

    result = " ".join(words)
    replacements = {
        "Narino": "Nariño",
        "Briceno": "Briceño",
    }
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result or None


LOCATION_STOP = (
    r"(?=\s+BARRIO|\s+SECTOR|\s+CONSTA|\s+CUENTA|\s+VALOR|\s+PRECIO|\s+PASTO|"
    r"\s+FSE|\s+INF|\s+INFORMES|\s+CON\s|\s+TIENE\s|\s+NEGOCIABLES|$)"
)


def clean_extracted_name(value):
    value = normalize_text(value)
    value = re.sub(r"^[\s\-:]+", "", value)
    value = re.split(
        r"\b("
        r"FSE|CONSTA|CUENTA|VALOR|PRECIO|PASTO|NARINO|INF|INFORMES|"
        r"UBICAD[OA]|SE\s+VENDE|VENTA|AREA|M2|MTS|HABITACION|HABITACIONES|"
        r"ALCOBAS|BANOS|COCINA|SALA|COMEDOR|PARQUEADERO|GARAJE|NEGOCIABLES|"
        r"ASCENSOR|PISCINA|CANCHAS|PATIO|ZONA\s+DE\s+LAVANDERIA"
        r")\b",
        value,
        maxsplit=1,
    )[0]
    value = re.sub(r"[^A-Z0-9\s\-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -")
    if len(value) <= 1:
        return None
    return smart_title(value)


def extract_conjunto_edificio(title, description):
    source = "\n".join(value for value in [title, description] if value)
    patterns = [
        rf"\b(CONJUNTO(?:\s+CERRADO|\s+RESIDENCIAL|\s+CAMPESTRE)?\s+[^\n]+?){LOCATION_STOP}",
        rf"\b(EDIF(?:ICIO|\.)?\s+[^\n]+?){LOCATION_STOP}",
        rf"\b(URB(?:ANIZACION|\.)?\s+[^\n]+?){LOCATION_STOP}",
        rf"\b(UNIDAD\s+RESIDENCIAL\s+[^\n]+?){LOCATION_STOP}",
        rf"\b(CONDOMINIO\s+[^\n]+?){LOCATION_STOP}",
        rf"\b(MIRADOR\s+TORRES?\s+DE\s+[^\n]+?){LOCATION_STOP}",
        rf"\b(TORRES?\s+DE\s+[^\n]+?){LOCATION_STOP}",
        rf"\b(RESERVAS?\s+DE\s+[^\n]+?){LOCATION_STOP}",
    ]

    for raw_line in source.splitlines():
        line = normalize_text(raw_line)
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                name = clean_extracted_name(match.group(1))
                if name:
                    return name

    return None


def extract_ph_value(text, edificio_conjunto=None):
    source = normalize_text(text)

    if re.search(r"\b(NO\s+PH|SIN\s+PH|NO\s+PROPIEDAD\s+HORIZONTAL|SIN\s+EDIFICIO)\b", source):
        return None
    if edificio_conjunto:
        return edificio_conjunto

    ph_keywords = [
        "PROPIEDAD HORIZONTAL",
        " P H ",
        " PH ",
        "CONJUNTO",
        "CONJUNTO CERRADO",
        "EDIFICIO",
        "UNIDAD RESIDENCIAL",
        "CONDOMINIO",
        "URBANIZACION CERRADA",
        "MIRADOR TORRES",
        "RESERVAS DE",
    ]

    if any(keyword in f" {source} " for keyword in ph_keywords):
        return "Si"

    return None


def extract_barrio(title, description):
    source = "\n".join(value for value in [title, description] if value)
    patterns = [
        rf"\bBARRIO\s+([A-Z0-9,\s\-]+?){LOCATION_STOP}",
        rf"\bSECTOR\s+([A-Z0-9,\s\-]+?){LOCATION_STOP}",
        rf"\bUBICAD[OA]\s+EN\s+(?:EL|LA)?\s*BARRIO\s+([A-Z0-9,\s\-]+?){LOCATION_STOP}",
        rf"\bUBICAD[OA]\s+EN\s+(?:EL|LA)?\s*SECTOR\s+([A-Z0-9,\s\-]+?){LOCATION_STOP}",
    ]

    for raw_line in source.splitlines():
        line = normalize_text(raw_line)
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                barrio = clean_extracted_name(match.group(1))
                if barrio:
                    return barrio

    return None


def extract_location_hint(title, description, edificio_conjunto=None):
    if edificio_conjunto:
        return edificio_conjunto

    source = "\n".join(value for value in [title, description] if value)
    patterns = [
        rf"\bUBICAD[OA]\s+EN\s+(?!LA\s+CIUDAD\b|EL\s+MUNICIPIO\b)(?:EL|LA|LOS|LAS)?\s*([A-Z0-9,\s\-]+?){LOCATION_STOP}",
        r"\bPLENO\s+CENTRO\b",
        r"\bEN\s+(?:EL|LA|LOS|LAS)?\s*(CENTRO|UNICENTRO|MORASURCO|PANDIACO|ALTAMIRA|AGUALONGO|ALFAGUARA|SOTAVENTO|MARILUZ|AQUINE|TAMASAGRA|CHAMPAGNAT|OBONUCO|CATAMBUCO|GENOY|BUESAQUILLO|GUALMATAN|CHACHAGUI|BUESACO|SANDONA|IPIALES)\b",
        rf"\b(?:POR|CERCA\s+A|CERCA\s+DE|A\s+DOS\s+CUADRAS\s+DE)\s+(?:EL|LA|LOS|LAS)?\s*([A-Z0-9,\s\-]+?){LOCATION_STOP}",
        rf"\bAVENIDA\s+([A-Z0-9,\s\-]+?){LOCATION_STOP}",
    ]

    for raw_line in source.splitlines():
        line = normalize_text(raw_line)
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                hint = "Centro" if match.lastindex is None else clean_extracted_name(match.group(1))
                if hint:
                    return hint

    return None


def extract_title_from_description(description):
    if not description:
        return None

    source = re.sub(r"^\s*FSE\s*\d+(?:-\d+)?\s*", "", description, flags=re.IGNORECASE)
    source = re.split(
        r"\b(CONSTA|CARACTERISTICAS|VALOR|PRECIO|CUENTA|UBICAD[OA]|INF|INFORMES)\b",
        source,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return clean_text(source)


def extract_city(title, description):
    source = normalize_text(f"{title or ''} {description or ''}")
    if "CHACHAGUI" in source:
        return "Chachagui"
    if "BUESACO" in source:
        return "Buesaco"
    if "ENCANO" in source:
        return "El Encano"
    return "Pasto"


def extract_area(text):
    source = normalize_text(text or "")
    patterns = [
        r"(?:AREA|AREA\s+CONSTRUIDA|AREA\s+TOTAL|AREA\s+DEL\s+LOTE)\s*(?:DE|:)?\s*(\d+(?:[\.,]\d+)?)\s*(?:M2|MTS|METROS)",
        r"(\d+(?:[\.,]\d+)?)\s*(?:M2|MTS|METROS\s+CUADRADOS)",
    ]
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def extract_count(text, patterns):
    source = normalize_text(text or "")
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            value = parse_small_int(match.group(1))
            if value is not None:
                return value
    return None


def number_pattern():
    return r"(\d+|UN|UNA|UNO|DOS|TRES|CUATRO|CINCO|SEIS|SIETE|OCHO|NUEVE|DIEZ)"


def extract_habitaciones(text):
    n = number_pattern()
    return extract_count(
        text,
        [
            rf"{n}\s+(?:HABITACIONES?|HABITACION|ALCOBAS?|CUARTOS?)",
            rf"(?:HABITACIONES?|HABITACION|ALCOBAS?|CUARTOS?)\s*[:\-]?\s*{n}",
        ],
    )


def extract_banios(text):
    n = number_pattern()
    return extract_count(
        text,
        [
            rf"{n}\s+(?:BAÑOS?|BANOS?|BA\S*OS?)",
            rf"(?:BAÑOS?|BANOS?|BA\S*OS?)\s*[:\-]?\s*{n}",
        ],
    )


def extract_parqueaderos(text):
    source = normalize_text(text or "")

    # "SIN PARQUEADERO" / "NO TIENE GARAJE" son afirmaciones negativas: hay que
    # descartarlas antes de buscar el conteo, o se terminaria reportando que SI
    # tiene parqueadero solo porque la palabra aparece en el texto.
    no_parqueadero = re.search(
        r"\bSIN\s+PARQUEADERO|\bSIN\s+GARAJE|\bNO\s+(?:TIENE\s+)?PARQUEADERO|\bNO\s+(?:TIENE\s+)?GARAJE",
        source,
    )

    n = number_pattern()
    count = extract_count(
        text,
        [
            rf"{n}\s+(?:PARQUEADEROS?|GARAJES?)",
            rf"(?:PARQUEADEROS?|GARAJES?)\s*[:\-]?\s*{n}",
        ],
    )
    if count is not None:
        return 0 if no_parqueadero else count

    if no_parqueadero:
        return 0

    if re.search(r"\b(PARQUEADERO|GARAJE|GARAJES)\b", source):
        return 1

    return None


def extract_administracion(text):
    source = normalize_text(text or "")
    patterns = [
        r"ADMINISTRACION\s*(?:DE|MENSUAL|VALOR)?\s*[:\-]?\s*\$?\s*([\d\.\,]+)",
        r"ADMIN\s*[:\-]?\s*\$?\s*([\d\.\,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            value = parse_money_digits(match.group(1))
            if value and value > 0:
                return value
    return None


def extract_antiguedad(text):
    source = normalize_text(text or "")
    match = re.search(
        r"ANTIGUEDAD\s*[:\-]?\s*((?:\d+\s*(?:A|A\s+)?\s*\d*\s*ANOS?)|NUEVO|USADO|PARA\s+ESTRENAR)",
        source,
    )
    if not match:
        return None

    value = match.group(1).replace("ANOS", "años")
    return smart_title(value)


def extract_pisos_totales(text):
    """
    Total de pisos del edificio/casa, ej. "3 PISOS". Requiere plural para no
    confundirse con "PISO 3" (que es la ubicacion del inmueble, no el total).
    """
    return extract_count(text, [r"(\d+)\s+PISOS\b"])


def extract_piso_ubicacion(text):
    """
    Piso en el que queda el inmueble, ej. "PISO 3". Se guarda aparte (en el
    JSON de detalles) para no mezclarlo con el total de pisos del edificio.
    """
    return extract_count(text, [r"\bPISO\s*[:\-]?\s*(\d+)\b"])


def extract_images(parser, page_url):
    image_urls = []
    seen = set()
    by_anuncio = {}

    for image in parser.images:
        src = image.get("src") or image.get("data-src")
        if not src:
            continue
        full_url = urljoin(page_url, src)
        if "/api/v1/anuncio/" not in full_url:
            continue
        match = re.search(r"/api/v1/anuncio/(\d+)/(imagen|thumb)", full_url)
        key = match.group(1) if match else full_url
        kind = match.group(2) if match else "imagen"
        current = by_anuncio.get(key)
        if not current or kind == "imagen":
            by_anuncio[key] = full_url

    for full_url in by_anuncio.values():
        if full_url not in seen:
            seen.add(full_url)
            image_urls.append(full_url)

    return image_urls


def extract_publication_data(url, tipo_hint=None):
    print(f"[INFO] Extrayendo publicacion Amorel: {url}")
    html, final_url = fetch_url(url)
    parser = parse_html(html)
    text = parser.text()
    lines = get_lines(text)
    title, published_at, category = extract_header(lines)
    description = extract_description(lines)
    if not title:
        title = extract_title_from_description(description)
    codigo = extract_codigo("\n".join(value for value in [title, description] if value), final_url)

    sale_ok, sale_reason = is_sale_listing(title, category, description or text)
    if not sale_ok:
        print(f"[SKIP] No es venta pura: {title} ({sale_reason})")
        return None, html, [], sale_reason

    full_detail_text = "\n".join(value for value in [title, category, description, text] if value)

    price = extract_price(full_detail_text)
    if not price:
        print(f"[SKIP] Venta sin precio real en detalle: {title}")
        return None, html, [], "sin_precio"

    tipo_inmueble = extract_property_type(title, category, full_detail_text, tipo_hint=tipo_hint)
    ciudad = extract_city(title, full_detail_text)
    edificio_conjunto = extract_conjunto_edificio(title, full_detail_text)
    barrio = (
        extract_barrio(title, full_detail_text)
        or extract_location_hint(title, full_detail_text, edificio_conjunto=edificio_conjunto)
    )
    ph = extract_ph_value(full_detail_text, edificio_conjunto=edificio_conjunto)
    location_result = resolve_pasto_location(
        barrio, title=title, description=full_detail_text, city=ciudad, ph=ph
    )
    print(f"[UBICACION] {location_diagnostic(location_result)}")
    if location_result.outside_municipality:
        return None, html, [], "fuera_de_pasto"
    barrio = location_result.value if location_result.accepted else None

    direccion_parts = [barrio, ciudad, "Nariño"]
    direccion = clean_text(", ".join(value for value in direccion_parts if value))

    image_urls = extract_images(parser, final_url)

    detalles_parseados = {
        "edificio_conjunto": edificio_conjunto,
        "categoria_amorel": category,
        "fecha_amorel": published_at,
        "precio_detectado_desde_detalle": price,
        "precio_negociable": is_price_negotiable(full_detail_text),
        "barrio_detectado": barrio,
        "normalizacion_ubicacion": location_diagnostic(location_result),
        "ph_detectado": ph,
        "piso_ubicacion": extract_piso_ubicacion(full_detail_text),
        "imagenes_detectadas": image_urls,
        "subcategoria_origen": tipo_hint,
        "fuente_busqueda": SEARCH_URL,
    }

    data = {
        "codigo_externo": codigo,
        "link_origen": final_url,
        "links_adicionales": json.dumps(detalles_parseados, ensure_ascii=False),
        "coordenadas": None,
        "latitud": None,
        "longitud": None,
        "direccion": direccion,
        "ciudad": ciudad,
        "barrio": barrio,
        "tipo_inmueble": tipo_inmueble,
        "ph": ph,
        "estrato": extract_count(full_detail_text, [r"ESTRATO\s*[:\-]?\s*(\d+)"]),
        "descripcion": description or clean_text(text),
        "precio": price,
        "m2": extract_area(full_detail_text),
        "m2_construido": None,
        "antiguedad": extract_antiguedad(full_detail_text),
        "pisos": extract_pisos_totales(full_detail_text),
        "habitaciones": extract_habitaciones(full_detail_text),
        "banios": extract_banios(full_detail_text),
        "parqueadero": extract_parqueaderos(full_detail_text),
        "administracion": extract_administracion(full_detail_text),
        "notas": None,
    }
    return data, html, image_urls, None


def get_connection():
    if mysql is None:
        raise RuntimeError("mysql-connector-python no esta instalado.")
    return mysql.connector.connect(**DB_CONFIG)


def get_or_create_fuente_id(connection):
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO fuentes_inmobiliarias
        (nombre, url_base, tipo_fuente, activa, descripcion)
        VALUES (%s, %s, %s, TRUE, %s)
        ON DUPLICATE KEY UPDATE
            id = LAST_INSERT_ID(id),
            activa = TRUE,
            url_base = VALUES(url_base),
            descripcion = VALUES(descripcion)
        """,
        (
            "Amorel Pasto",
            BASE_URL,
            "portal",
            "Scraper de clasificados inmobiliarios en venta desde Amorel Pasto",
        ),
    )
    connection.commit()
    fuente_id = cursor.lastrowid
    cursor.close()
    return fuente_id


def publicacion_ya_existe(connection, link_origen=None, fuente_id=None, codigo_externo=None):
    cursor = connection.cursor()
    if codigo_externo and fuente_id:
        cursor.execute(
            """
            SELECT id
            FROM publicaciones
            WHERE link_origen = %s
               OR (fuente_id = %s AND codigo_externo = %s)
            LIMIT 1
            """,
            (link_origen, fuente_id, codigo_externo),
        )
    else:
        cursor.execute(
            """
            SELECT id
            FROM publicaciones
            WHERE link_origen = %s
            LIMIT 1
            """,
            (link_origen,),
        )
    result = cursor.fetchone()
    cursor.close()
    return result[0] if result else None


def insert_publicacion(connection, data):
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO publicaciones (
            fuente_id, codigo_externo, link_origen, links_adicionales,
            coordenadas, latitud, longitud, direccion, ciudad, barrio,
            tipo_inmueble, ph, estrato, descripcion, precio, m2,
            m2_construido, antiguedad, pisos, habitaciones, banios,
            parqueadero, administracion, notas
        )
        VALUES (
            %(fuente_id)s, %(codigo_externo)s, %(link_origen)s, %(links_adicionales)s,
            %(coordenadas)s, %(latitud)s, %(longitud)s, %(direccion)s, %(ciudad)s, %(barrio)s,
            %(tipo_inmueble)s, %(ph)s, %(estrato)s, %(descripcion)s, %(precio)s, %(m2)s,
            %(m2_construido)s, %(antiguedad)s, %(pisos)s, %(habitaciones)s, %(banios)s,
            %(parqueadero)s, %(administracion)s, %(notas)s
        )
        """,
        data,
    )
    connection.commit()
    publicacion_id = cursor.lastrowid
    cursor.close()
    return publicacion_id


def insert_evidencia(connection, publicacion_id, tipo, ruta_archivo, url_original=None):
    ruta_archivo = str(ruta_archivo) if ruta_archivo else None
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id
        FROM evidencias_publicacion
        WHERE publicacion_id = %s
          AND tipo = %s
          AND ruta_archivo = %s
        LIMIT 1
        """,
        (publicacion_id, tipo, ruta_archivo),
    )
    if cursor.fetchone():
        cursor.close()
        return

    cursor.execute(
        """
        INSERT INTO evidencias_publicacion
        (publicacion_id, tipo, ruta_archivo, url_original, hash_archivo)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (publicacion_id, tipo, ruta_archivo, url_original, file_hash(ruta_archivo)),
    )
    connection.commit()
    cursor.close()


def get_publication_evidence_dirs(publicacion_id):
    base_dir = EVIDENCE_DIR / f"publicacion_{publicacion_id}"
    html_dir = base_dir / "html"
    img_dir = base_dir / "imagenes"
    for folder in [html_dir, img_dir]:
        folder.mkdir(parents=True, exist_ok=True)
    return html_dir, img_dir


def sanitize_filename(value):
    value = clean_text(value) or str(int(time.time()))
    value = re.sub(r"[^a-zA-Z0-9_-]", "_", value)
    return value[:120]


def file_hash(path):
    if not path or not Path(path).exists():
        return None
    sha256 = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def make_standalone_html(html, page_url):
    if not page_url:
        return html

    base_tag = f'<base href="{html_module.escape(page_url, quote=True)}">'
    meta_tag = '<meta charset="utf-8">'

    if re.search(r"<base\b", html or "", flags=re.IGNORECASE):
        html_with_base = html
    elif re.search(r"<head[^>]*>", html or "", flags=re.IGNORECASE):
        html_with_base = re.sub(
            r"(<head[^>]*>)",
            rf"\1\n{meta_tag}\n{base_tag}",
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        html_with_base = f"<!doctype html><html><head>{meta_tag}{base_tag}</head><body>{html}</body></html>"

    return html_with_base


def save_html(html, codigo_archivo, publicacion_id, page_url=None):
    html_dir, _ = get_publication_evidence_dirs(publicacion_id)
    path = html_dir / f"amorel_{sanitize_filename(codigo_archivo)}.html"
    with open(path, "w", encoding="utf-8") as file:
        file.write(make_standalone_html(html, page_url))
    return path


def download_image(image_url, codigo_archivo, index, publicacion_id):
    _, img_dir = get_publication_evidence_dirs(publicacion_id)
    filename = f"amorel_{sanitize_filename(codigo_archivo)}_{index:02d}.jpg"
    path = img_dir / filename
    try:
        request = Request(safe_url(image_url), headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=IMAGE_DOWNLOAD_TIMEOUT) as response:
            content = response.read()
        if not content:
            return None
        with open(path, "wb") as file:
            file.write(content)
        return path
    except (URLError, TimeoutError, OSError) as error:
        print(f"[WARN] No se pudo descargar imagen {image_url}: {error}")
        return None


def download_images_parallel(image_urls, codigo_archivo, publicacion_id):
    if not image_urls:
        return []

    workers = max(1, min(IMAGE_DOWNLOAD_WORKERS, len(image_urls)))
    downloaded = []
    print(f"[INFO] Descargando {len(image_urls)} imagenes Amorel con {workers} hilos")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_image, image_url, codigo_archivo, index, publicacion_id): (index, image_url)
            for index, image_url in enumerate(image_urls, start=1)
        }
        for future in as_completed(futures):
            index, image_url = futures[future]
            image_path = future.result()
            if image_path:
                downloaded.append((index, image_url, image_path))
                print(f"[OK] Imagen descargada {index}/{len(image_urls)}")
    downloaded.sort(key=lambda item: item[0])
    return downloaded


def main():
    print("[INFO] Iniciando scraper Amorel Pasto (solo VENTAS)")
    print(f"[INFO] SEARCH_URL base: {SEARCH_URL}")
    print(f"[INFO] Subcategorias de venta a recorrer: {[s for s, _ in SALE_SUBCATEGORIES]}")
    print(f"[INFO] AMOREL_MAX_PAGES (por subcategoria): {MAX_PAGES if MAX_PAGES > 0 else 'sin limite'}")
    print(f"[INFO] AMOREL_MIN_SALE_PRICE: {MIN_SALE_PRICE}")

    publication_links, audit = collect_publication_links()
    print(f"[INFO] Total links Amorel encontrados (solo venta): {len(publication_links)}")

    connection = get_connection()
    fuente_id = get_or_create_fuente_id(connection)

    total_nuevas = 0
    total_saltadas = 0
    total_omitidas = 0
    total_errores = 0

    for index, (link, tipo_hint) in enumerate(publication_links, start=1):
        print(f"\n[INFO] Procesando Amorel {index}/{len(publication_links)}")
        print(f"[INFO] Link: {link}")
        try:
            data, html, image_urls, skip_reason = extract_publication_data(link, tipo_hint=tipo_hint)
            if not data:
                total_omitidas += 1
                audit.record_omission(skip_reason or "sin_datos_extraidos", link)
                continue

            data["fuente_id"] = fuente_id
            publicacion_existente_id = publicacion_ya_existe(
                connection,
                link_origen=data.get("link_origen"),
                fuente_id=fuente_id,
                codigo_externo=data.get("codigo_externo"),
            )
            if publicacion_existente_id:
                total_saltadas += 1
                html_path = save_html(
                    html,
                    data.get("codigo_externo"),
                    publicacion_existente_id,
                    data.get("link_origen"),
                )
                insert_evidencia(connection, publicacion_existente_id, "html", html_path, data.get("link_origen"))
                print(f"[SKIP] Ya existe en base de datos. ID {publicacion_existente_id}")
                continue

            try:
                publicacion_id = insert_publicacion(connection, data)
            except IntegrityError:
                publicacion_existente_id = publicacion_ya_existe(
                    connection,
                    link_origen=data.get("link_origen"),
                    fuente_id=fuente_id,
                    codigo_externo=data.get("codigo_externo"),
                )
                if publicacion_existente_id:
                    total_saltadas += 1
                    html_path = save_html(
                        html,
                        data.get("codigo_externo"),
                        publicacion_existente_id,
                        data.get("link_origen"),
                    )
                    insert_evidencia(connection, publicacion_existente_id, "html", html_path, data.get("link_origen"))
                    print(f"[SKIP] Ya existia al momento de insertar. ID {publicacion_existente_id}")
                    continue
                raise

            total_nuevas += 1
            codigo_archivo = data.get("codigo_externo") or f"publicacion_{publicacion_id}"
            html_path = save_html(html, codigo_archivo, publicacion_id, data.get("link_origen"))
            insert_evidencia(connection, publicacion_id, "html", html_path, data.get("link_origen"))

            print(f"[INFO] Imagenes detectadas: {len(image_urls)}")
            for _, image_url, image_path in download_images_parallel(image_urls, codigo_archivo, publicacion_id):
                insert_evidencia(connection, publicacion_id, "imagen", image_path, image_url)

            detect_duplicates_safely(connection, publicacion_id)

            print(f"[OK] Guardada publicacion Amorel ID {publicacion_id}")
            print(f"[OK] Codigo externo: {data['codigo_externo']}")
            print(f"[OK] Tipo: {data['tipo_inmueble']} | Barrio: {data['barrio']} | Ciudad: {data['ciudad']}")
            print(f"[OK] Precio: {data['precio']} | Area: {data['m2']}")

            if REQUEST_PAUSE_SECONDS > 0:
                time.sleep(REQUEST_PAUSE_SECONDS)

        except Exception as error:
            total_errores += 1
            audit.record_error(link, error)
            print(f"[ERROR] Fallo publicacion Amorel {link}: {error}")

    connection.close()

    print("\n[OK] Scraping Amorel finalizado.")
    print(f"[RESUMEN] Nuevas guardadas: {total_nuevas}")
    print(f"[RESUMEN] Saltadas porque ya existian: {total_saltadas}")
    print(f"[RESUMEN] Omitidas por filtro/precio: {total_omitidas}")
    print(f"[RESUMEN] Errores: {total_errores}")
    audit.set_processing_counts(
        nuevas=total_nuevas,
        saltadas=total_saltadas,
        omitidas=total_omitidas,
        errores=total_errores,
    )
    audit.print_summary(len(publication_links))
    audit.save(len(publication_links))


if __name__ == "__main__":
    main()
