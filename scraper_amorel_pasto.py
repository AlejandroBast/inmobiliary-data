import json
import os
import re
import time
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from mysql.connector import IntegrityError
from scraper_audit import ScraperAudit
from functools import partial

from scrapers.core.config import get_db_config
from scrapers.core.db import (
    get_connection as core_get_connection,
    get_or_create_fuente_id as core_get_or_create_fuente_id,
    insert_evidencia,
    insert_publicacion,
    publicacion_ya_existe,
)
from scrapers.core.evidence import (
    get_publication_evidence_dirs,
    sanitize_filename,
    save_html as core_save_html,
    download_images_parallel as core_download_images_parallel,
)
from scrapers.core.stats import print_scraper_summary, skip_bucket
from scrapers.core.normalizers import (
    clean_text,
    detect_ph as core_detect_ph,
    extract_barrio as core_extract_barrio,
    parse_area as core_parse_area,
    parse_price as core_parse_price,
    sale_status as core_sale_status,
)

SEARCH_URL = os.getenv(
    "AMOREL_SEARCH_URL",
    "https://amorelpasto.com/clasificados/web/app.php/resultados/Finca%20Raiz",
)
BASE_URL = "https://amorelpasto.com"
DB_CONFIG = get_db_config()
EVIDENCE_PREFIX = "amorel"
get_connection = partial(core_get_connection, db_config=DB_CONFIG)
get_or_create_fuente_id = partial(
    core_get_or_create_fuente_id,
    nombre="Amorel Pasto",
    url_base=BASE_URL,
    tipo_fuente="portal",
    descripcion="Scraper de clasificados inmobiliarios en venta desde Amorel Pasto.",
)
save_html = partial(core_save_html, prefix=EVIDENCE_PREFIX)

# 0 = all pages detected from the Amorel pagination.
MAX_PAGES = int(os.getenv("AMOREL_MAX_PAGES", "0"))
REQUEST_PAUSE_SECONDS = float(os.getenv("REQUEST_PAUSE_SECONDS", "0.5"))
IMAGE_DOWNLOAD_WORKERS = int(os.getenv("IMAGE_DOWNLOAD_WORKERS", "6"))
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "12"))
MIN_SALE_PRICE = int(os.getenv("AMOREL_MIN_SALE_PRICE", "10000000"))

EVIDENCE_DIR = Path("evidencias")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

NEGATIVE_TITLE_KEYWORDS = [
    "ARRIENDO",
    "ARRIENDA",
    "ARRENDA",
    "ARRENDAR",
    "RENTA",
    "RENTO",
    "ALQUILA",
    "ALQUILER",
    "ANTICRES",
    "ANTICRESA",
    "ANTICRESO",
    "PERMUTO",
    "PERMUTA",
    "BUSCO",
    "BUSCA",
    "BUSQUEDA",
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

def normalize_text(value):
    value = clean_text(value) or ""
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
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

def is_results_page_url(url):
    if not is_amorel_url(url):
        return False
    if is_publication_url(url):
        return False
    normalized = normalize_text(url)
    return (
        "/resultados/" in url
        or "PAGINA=" in normalized
        or "PAGE=" in normalized
        or "Finca%20Raiz" in url
        or "Finca Raiz" in unquote(url)
    )

def build_page_url(page_number):
    if page_number <= 1:
        return SEARCH_URL

    parts = urlsplit(SEARCH_URL)
    query = parts.query
    if re.search(r"(^|&)pagina=\d+", query):
        query = re.sub(r"(^|&)pagina=\d+", rf"\1pagina={page_number}", query)
    else:
        query = f"{query}&pagina={page_number}" if query else f"pagina={page_number}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

def collect_publication_links():
    """
    Recorre Amorel con dos estrategias:
    1) Sigue los enlaces reales de paginacion que entrega la pagina.
    2) Hace respaldo secuencial con ?pagina=N hasta que aparezcan paginas sin links nuevos.

    Esto corrige el problema de revisar solo una parte de los resultados cuando
    la paginacion no aparece exactamente como ?pagina=N en el HTML.
    """
    audit = ScraperAudit("Amorel", SEARCH_URL)
    all_links = []
    seen_publications = set()
    seen_pages = set()
    queued_pages = set()
    pages_scanned = 0
    page_sequence = 0

    def queue_results_page(raw_link, page_url, queue):
        full_url = canonicalize_url(urljoin(page_url, raw_link))
        if not is_results_page_url(full_url):
            return
        if full_url in seen_pages or full_url in queued_pages:
            return
        queued_pages.add(full_url)
        queue.append(full_url)

    def scan_page(page_url, queue=None, source_label="auto"):
        nonlocal pages_scanned, page_sequence

        page_url = canonicalize_url(page_url)
        if page_url in seen_pages:
            return 0, 0, True

        if MAX_PAGES > 0 and pages_scanned >= MAX_PAGES:
            return 0, 0, False

        page_sequence += 1
        try:
            html, final_url = fetch_url(page_url)
            final_url = canonicalize_url(final_url)
        except Exception as error:
            reason = f"No se pudo abrir la pagina {page_url}: {error}"
            print(f"[WARN] {reason}")
            audit.record_page(page_sequence, url=page_url, status="error", reason=reason)
            seen_pages.add(page_url)
            pages_scanned += 1
            return 0, 0, False

        seen_pages.add(page_url)
        seen_pages.add(final_url)
        pages_scanned += 1

        parser = parse_html(html)
        page_seen = set()
        page_links_count = 0
        new_links_count = 0
        duplicate_links_count = 0

        for link_text, href in parser.links:
            full_url = canonicalize_url(urljoin(final_url, href))

            if is_publication_url(full_url):
                publicacion_id = extract_publication_id(full_url)
                if not publicacion_id or publicacion_id in page_seen:
                    continue
                page_seen.add(publicacion_id)
                page_links_count += 1

                if publicacion_id in seen_publications:
                    duplicate_links_count += 1
                else:
                    seen_publications.add(publicacion_id)
                    all_links.append(full_url)
                    new_links_count += 1
                continue

            if queue is not None:
                queue_results_page(href, final_url, queue)

        audit.record_page(
            page_sequence,
            url=page_url,
            links_count=page_links_count,
            new_links_count=new_links_count,
            duplicate_links_count=duplicate_links_count,
            status="ok",
            reason=source_label,
        )
        print(
            f"[INFO] Pagina {page_sequence}: {page_links_count} links, "
            f"{new_links_count} nuevos, {duplicate_links_count} repetidos | {page_url}"
        )
        return page_links_count, new_links_count, True

    queue = [canonicalize_url(SEARCH_URL)]
    queued_pages.add(canonicalize_url(SEARCH_URL))

    while queue:
        page_url = queue.pop(0)
        scan_page(page_url, queue=queue, source_label="paginacion_html")
        if MAX_PAGES > 0 and pages_scanned >= MAX_PAGES:
            break

    # Respaldo: algunas versiones de Amorel no muestran toda la paginacion en el HTML.
    # Probamos ?pagina=N y paramos cuando dos paginas seguidas no traen links nuevos.
    empty_streak = 0
    sequential_page = 2
    while MAX_PAGES == 0 or pages_scanned < MAX_PAGES:
        candidate_url = canonicalize_url(build_page_url(sequential_page))
        sequential_page += 1

        if candidate_url in seen_pages:
            continue

        links_count, new_links_count, ok = scan_page(
            candidate_url,
            queue=None,
            source_label="respaldo_secuencial",
        )
        if not ok:
            empty_streak += 1
        elif links_count == 0 or new_links_count == 0:
            empty_streak += 1
        else:
            empty_streak = 0

        if empty_streak >= 2:
            break

    limit_reason = None
    if MAX_PAGES > 0:
        limit_reason = f"AMOREL_MAX_PAGES={MAX_PAGES}; el recorrido se detuvo al llegar a ese limite."

    audit.set_listing_summary(
        total_reported=None,
        pages_expected=None,
        pages_planned=pages_scanned,
        page_size=None,
        limit_reason=limit_reason,
    )

    print(f"[INFO] Paginas Amorel revisadas: {pages_scanned}")
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
    core_price = core_parse_price(text)
    if core_price and core_price >= MIN_SALE_PRICE:
        return core_price

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

def is_sale_listing(title, category, description):
    sale_ok, sale_reason = core_sale_status(f"{title or ''}\n{category or ''}\n{description or ''}")
    if not sale_ok:
        return False, "no_es_venta_pura" if sale_reason == "no_venta" else sale_reason
    return True, None

    title_category = normalize_text(f"{title or ''} {category or ''}")
    if any(keyword in title_category for keyword in NEGATIVE_TITLE_KEYWORDS):
        return False, "no_es_venta_pura"

    if any(keyword in title_category for keyword in SALE_KEYWORDS):
        return True, None

    description_norm = normalize_text(description)
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

def extract_property_type(title, category, description):
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

def clean_extracted_name(value):
    value = normalize_text(value)
    value = re.sub(r"^[\s\-:]+", "", value)
    value = re.split(
        r"\b("
        r"FSE|CONSTA|CUENTA|VALOR|PRECIO|PASTO|NARINO|NARIÑO|"
        r"UBICAD[OA]|SE\s+VENDE|VENTA|AREA|ÁREA|M2|MTS|"
        r"HABITACION|HABITACIONES|ALCOBAS|BAÑOS|BANOS|"
        r"COCINA|SALA|COMEDOR|PARQUEADERO|GARAJE|"
        r"AL\s+NORTE|AL\s+SUR|AL\s+ORIENTE|AL\s+OCCIDENTE"
        r")\b",
        value,
        maxsplit=1,
    )[0]
    value = re.sub(r"[^A-Z0-9Ñ\s\-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -")
    if len(value) <= 1:
        return None
    return smart_title(value)

def extract_conjunto_edificio(title, description):
    source = "\n".join(value for value in [title, description] if value)

    patterns = [
        r"\bCONJUNTO(?:\s+CERRADO)?\s*[-:]?\s*([A-Z0-9Ñ\s\-]+?)(?=\s+BARRIO|\s+SECTOR|\s+CONSTA|\s+CUENTA|\s+VALOR|\s+FSE|$)",
        r"\bEDIFICIO\s+([A-Z0-9Ñ\s\-]+?)(?=\s+BARRIO|\s+SECTOR|\s+CONSTA|\s+CUENTA|\s+VALOR|\s+FSE|$)",
        r"\bUNIDAD\s+RESIDENCIAL\s+([A-Z0-9Ñ\s\-]+?)(?=\s+BARRIO|\s+SECTOR|\s+CONSTA|\s+CUENTA|\s+VALOR|\s+FSE|$)",
        r"\bCONDOMINIO\s+([A-Z0-9Ñ\s\-]+?)(?=\s+BARRIO|\s+SECTOR|\s+CONSTA|\s+CUENTA|\s+VALOR|\s+FSE|$)",
    ]

    for raw_line in source.splitlines():
        line = normalize_text(raw_line)
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                name = clean_extracted_name(match.group(1))
                if name:
                    return name

    return None

def extract_ph_value(text, edificio_conjunto=None):
    source = normalize_text(text)

    if re.search(r"\b(NO\s+PH|SIN\s+PH|NO\s+PROPIEDAD\s+HORIZONTAL|SIN\s+EDIFICIO)\b", source):
        return None

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
    ]

    if edificio_conjunto or any(keyword in f" {source} " for keyword in ph_keywords):
        return 1

    return None

def extract_barrio(title, description):
    """
    Identifica barrio desde titulo o detalle. Es obligatorio para guardar,
    pero se calcula desde texto libre porque Amorel no lo trae estructurado.
    """
    source = "\n".join(value for value in [title, description] if value)

    patterns = [
        r"\bBARRIO\s+([A-Z0-9Ñ\s\-]+)",
        r"\bSECTOR\s+([A-Z0-9Ñ\s\-]+)",
        r"\bUBICAD[OA]\s+EN\s+(?:EL|LA)?\s*BARRIO\s+([A-Z0-9Ñ\s\-]+)",
        r"\bUBICAD[OA]\s+EN\s+(?:EL|LA)?\s*SECTOR\s+([A-Z0-9Ñ\s\-]+)",
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
    return core_parse_area(text)

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
    n = number_pattern()
    count = extract_count(
        text,
        [
            rf"{n}\s+(?:PARQUEADEROS?|GARAJES?)",
            rf"(?:PARQUEADEROS?|GARAJES?)\s*[:\-]?\s*{n}",
        ],
    )
    if count is not None:
        return count

    if re.search(r"\b(PARQUEADERO|GARAJE|GARAJES)\b", normalize_text(text or "")):
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

LOCATION_STOP = (
    r"(?=\s+BARRIO|\s+SECTOR|\s+CONSTA|\s+CUENTA|\s+VALOR|\s+PRECIO|\s+PASTO|"
    r"\s+FSE|\s+INF|\s+INFORMES|\s+CON\s|\s+TIENE\s|\s+NEGOCIABLES|$)"
)

def clean_extracted_name(value):
    value = normalize_text(value)
    value = re.sub(r"^[\s\-:]+", "", value)
    value = re.split(
        r"\b("
        r"FSE|CONSTA|CUENTA|VALOR|PRECIO|PASTO|NARINO|NARINO|INF|INFORMES|"
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

    return core_detect_ph(text)

def extract_barrio(title, description):
    source = "\n".join(value for value in [title, description] if value)
    core_barrio = core_extract_barrio(source)
    if core_barrio:
        return core_barrio

    patterns = [
        rf"\bBARRIO\s+([A-Z0-9\s\-]+?){LOCATION_STOP}",
        rf"\bSECTOR\s+([A-Z0-9\s\-]+?){LOCATION_STOP}",
        rf"\bUBICAD[OA]\s+EN\s+(?:EL|LA)?\s*BARRIO\s+([A-Z0-9\s\-]+?){LOCATION_STOP}",
        rf"\bUBICAD[OA]\s+EN\s+(?:EL|LA)?\s*SECTOR\s+([A-Z0-9\s\-]+?){LOCATION_STOP}",
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
        rf"\bUBICAD[OA]\s+EN\s+(?!LA\s+CIUDAD\b|EL\s+MUNICIPIO\b)(?:EL|LA|LOS|LAS)?\s*([A-Z0-9\s\-]+?){LOCATION_STOP}",
        r"\bPLENO\s+CENTRO\b",
        r"\bEN\s+(?:EL|LA|LOS|LAS)?\s*(CENTRO|UNICENTRO|MORASURCO|PANDIACO|ALTAMIRA|AGUALONGO|ALFAGUARA|SOTAVENTO|MARILUZ|AQUINE|TAMASAGRA|CHAMPAGNAT|OBONUCO|CATAMBUCO|GENOY|BUESAQUILLO|GUALMATAN|CHACHAGUI|BUESACO|SANDONA|IPIALES)\b",
        rf"\b(?:POR|CERCA\s+A|CERCA\s+DE|A\s+DOS\s+CUADRAS\s+DE)\s+(?:EL|LA|LOS|LAS)?\s*([A-Z0-9\s\-]+?){LOCATION_STOP}",
        rf"\bAVENIDA\s+([A-Z0-9\s\-]+?){LOCATION_STOP}",
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
        r"\b(CONSTA|CARACTERISTICAS|CARACTERISTICAS|VALOR|PRECIO|CUENTA|UBICAD[OA]|INF|INFORMES)\b",
        source,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return clean_text(source)

def extract_publication_data(url):
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

    tipo_inmueble = extract_property_type(title, category, full_detail_text)
    ciudad = extract_city(title, full_detail_text)
    edificio_conjunto = extract_conjunto_edificio(title, full_detail_text)
    barrio = (
        extract_barrio(title, full_detail_text)
        or extract_location_hint(title, full_detail_text, edificio_conjunto=edificio_conjunto)
    )
    if not barrio:
        print(f"[SKIP] Venta con precio pero sin barrio identificable: {title}")
        return None, html, [], "sin_barrio"

    ph = extract_ph_value(full_detail_text, edificio_conjunto=edificio_conjunto)

    direccion_parts = [barrio, ciudad, "Nariño"]
    direccion = clean_text(", ".join(value for value in direccion_parts if value))

    image_urls = extract_images(parser, final_url)

    detalles_parseados = {
        "edificio_conjunto": edificio_conjunto,
        "categoria_amorel": category,
        "fecha_amorel": published_at,
        "precio_detectado_desde_detalle": price,
        "barrio_detectado": barrio,
        "ph_detectado": ph,
        "imagenes_detectadas": image_urls,
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
        "pisos": extract_count(full_detail_text, [r"(\d+)\s+PISOS?", r"PISO\s*[:\-]?\s*(\d+)"]),
        "habitaciones": extract_habitaciones(full_detail_text),
        "banios": extract_banios(full_detail_text),
        "parqueadero": extract_parqueaderos(full_detail_text),
        "administracion": extract_administracion(full_detail_text),
        "notas": None,
    }
    return data, html, image_urls, None

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

download_images_parallel = partial(
    core_download_images_parallel,
    download_image_func=download_image,
    image_download_workers=IMAGE_DOWNLOAD_WORKERS,
    label="imagenes Amorel",
)

def main():
    print("[INFO] Iniciando scraper Amorel Pasto")
    print("[INFO] Fuente revisada: Amorel Pasto")
    print(f"[INFO] SEARCH_URL: {SEARCH_URL}")
    print(f"[INFO] AMOREL_MAX_PAGES: {MAX_PAGES if MAX_PAGES > 0 else 'sin limite'}")
    print(f"[INFO] AMOREL_MIN_SALE_PRICE: {MIN_SALE_PRICE}")

    publication_links, audit = collect_publication_links()
    print(f"[INFO] Total links Amorel encontrados: {len(publication_links)}")

    connection = get_connection()
    fuente_id = get_or_create_fuente_id(connection)

    total_nuevas = 0
    total_saltadas = 0
    total_omitidas = 0
    total_sin_precio = 0
    total_no_venta = 0
    total_sin_barrio = 0
    total_errores = 0

    for index, link in enumerate(publication_links, start=1):
        print(f"\n[INFO] Procesando Amorel {index}/{len(publication_links)}")
        print(f"[INFO] Link: {link}")
        try:
            data, html, image_urls, skip_reason = extract_publication_data(link)
            if not data:
                total_omitidas += 1
                bucket = skip_bucket(skip_reason)
                if bucket == "sin_precio":
                    total_sin_precio += 1
                elif bucket == "no_venta":
                    total_no_venta += 1
                elif bucket == "sin_barrio":
                    total_sin_barrio += 1
                else:
                    total_errores += 1
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
    print_scraper_summary(
        fuente="Amorel Pasto",
        total_encontrado=len(publication_links),
        guardadas=total_nuevas,
        descartadas_sin_precio=total_sin_precio,
        descartadas_no_venta=total_no_venta,
        descartadas_sin_barrio=total_sin_barrio,
        duplicadas=total_saltadas,
        errores=total_errores,
    )
    audit.set_processing_counts(
        nuevas=total_nuevas,
        saltadas=total_saltadas,
        omitidas=total_omitidas,
        omitidas_sin_precio=total_sin_precio,
        omitidas_no_venta=total_no_venta,
        omitidas_sin_barrio=total_sin_barrio,
        errores=total_errores,
    )
    audit.print_summary(len(publication_links))
    audit.save(len(publication_links))

if __name__ == "__main__":
    main()
