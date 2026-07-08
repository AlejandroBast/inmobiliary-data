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

from scraper_audit import ScraperAudit


load_dotenv()

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


def extract_publication_id(url):
    match = re.search(r"/publicacion/(\d+)", url)
    return match.group(1) if match else None


def build_page_url(page_number):
    if page_number <= 1:
        return SEARCH_URL
    separator = "&" if "?" in SEARCH_URL else "?"
    return f"{SEARCH_URL}{separator}pagina={page_number}"


def collect_publication_links():
    audit = ScraperAudit("Amorel", SEARCH_URL)
    all_links = []
    seen = set()

    try:
        first_html, _ = fetch_url(build_page_url(1))
    except Exception as error:
        reason = f"No se pudo abrir la primera pagina de resultados: {error}"
        print(f"[ERROR] {reason}")
        audit.record_page(1, url=build_page_url(1), status="error", reason=reason)
        return [], audit

    first_parser = parse_html(first_html)
    page_numbers = [1]
    for text, href in first_parser.links:
        full_url = urljoin(SEARCH_URL, href)
        match = re.search(r"[?&]pagina=(\d+)", full_url)
        if match:
            page_numbers.append(int(match.group(1)))

    detected_pages = max(page_numbers) if page_numbers else 1
    pages_to_scan = min(detected_pages, MAX_PAGES) if MAX_PAGES > 0 else detected_pages
    limit_reason = None
    if MAX_PAGES > 0 and detected_pages > pages_to_scan:
        limit_reason = (
            f"Se revisaron {pages_to_scan} de {detected_pages} pagina(s) porque "
            f"AMOREL_MAX_PAGES={MAX_PAGES} limito el recorrido."
        )

    audit.set_listing_summary(
        total_reported=None,
        pages_expected=detected_pages,
        pages_planned=pages_to_scan,
        page_size=None,
        limit_reason=limit_reason,
    )

    print(f"[INFO] Paginas Amorel detectadas: {detected_pages}")
    print(f"[INFO] Paginas Amorel a revisar: {pages_to_scan}")

    for page_number in range(1, pages_to_scan + 1):
        page_url = build_page_url(page_number)
        try:
            if page_number == 1:
                html = first_html
            else:
                html, _ = fetch_url(page_url)
        except Exception as error:
            reason = f"No se pudo abrir la pagina {page_number}: {error}"
            print(f"[WARN] {reason}")
            audit.record_page(page_number, url=page_url, status="error", reason=reason)
            continue

        parser = parse_html(html)
        page_links = []
        page_seen = set()

        for text, href in parser.links:
            full_url = urljoin(page_url, href)
            if "/publicacion/" not in full_url:
                continue
            publicacion_id = extract_publication_id(full_url)
            if not publicacion_id or publicacion_id in page_seen:
                continue
            page_seen.add(publicacion_id)
            page_links.append(full_url)

        new_links = 0
        duplicate_links = 0
        for link in page_links:
            publicacion_id = extract_publication_id(link) or link
            if publicacion_id in seen:
                duplicate_links += 1
            else:
                seen.add(publicacion_id)
                all_links.append(link)
                new_links += 1

        audit.record_page(
            page_number,
            url=page_url,
            links_count=len(page_links),
            new_links_count=new_links,
            duplicate_links_count=duplicate_links,
        )
        print(
            f"[INFO] Pagina {page_number}/{pages_to_scan}: "
            f"{len(page_links)} links, {new_links} nuevos, {duplicate_links} repetidos"
        )

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
    candidates = []
    source = text or ""

    for match in re.finditer(r"\$\s*([\d][\d\s\.,']{3,})", source):
        value = parse_money_digits(match.group(1))
        if value and value >= MIN_SALE_PRICE:
            candidates.append(value)

    million_pattern = r"(\d+(?:[\.,]\d+)?)\s*(?:MILLONES|MILLON|MILLON)"
    for match in re.finditer(million_pattern, normalize_text(source)):
        number = match.group(1).replace(",", ".")
        try:
            value = int(float(number) * 1_000_000)
        except ValueError:
            continue
        if value >= MIN_SALE_PRICE:
            candidates.append(value)

    return max(candidates) if candidates else None


def is_sale_listing(title, category, description):
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
    match = re.search(r"\bFSE\s*(\d+)\b", text or "", re.IGNORECASE)
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


def extract_barrio(title, description):
    patterns = [
        r"\bBARRIO\s+([A-Z0-9 ]+)",
        r"\bSECTOR\s+([A-Z0-9 ]+)",
    ]
    for raw_line in f"{title or ''}\n{description or ''}".splitlines():
        source = normalize_text(raw_line)
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                value = clean_text(match.group(1))
                if not value:
                    continue
                value = re.split(
                    r"\b(PASTO|CHACHAGUI|NARINO|CONJUNTO|EDIFICIO|FSE|SE VENDE|VENTA|CONSTA|UBICADO)\b",
                    value,
                )[0]
                value = clean_text(value)
                if value:
                    return value.title()
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
    source = text or ""
    patterns = [
        r"(?:AREA|.REA)\s+(?:DEL\s+LOTE\s+)?(?:DE\s+)?(\d+(?:[\.,]\d+)?)\s*(?:M2|MTS|METROS)",
        r"(\d+(?:[\.,]\d+)?)\s*(?:M2|MTS|METROS\s+CUADRADOS)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalize_text(source))
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def extract_count(text, patterns):
    source = normalize_text(text)
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


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


def extract_publication_data(url):
    print(f"[INFO] Extrayendo publicacion Amorel: {url}")
    html, final_url = fetch_url(url)
    parser = parse_html(html)
    text = parser.text()
    lines = get_lines(text)
    title, published_at, category = extract_header(lines)
    description = extract_description(lines)
    codigo = extract_codigo(text, final_url)

    sale_ok, sale_reason = is_sale_listing(title, category, description)
    if not sale_ok:
        print(f"[SKIP] No es venta pura: {title} ({sale_reason})")
        return None, html, [], sale_reason

    price = extract_price("\n".join([title or "", category or "", text or ""]))
    if not price:
        print(f"[SKIP] Venta sin precio real mayor a cero: {title}")
        return None, html, [], "sin_precio"

    tipo_inmueble = extract_property_type(title, category, description)
    barrio = extract_barrio(title, description)
    ciudad = extract_city(title, description)
    direccion = clean_text(", ".join(value for value in [barrio, ciudad, "Narino"] if value))
    image_urls = extract_images(parser, final_url)

    data = {
        "codigo_externo": codigo,
        "link_origen": final_url,
        "links_adicionales": json.dumps(
            {
                "fuente_busqueda": SEARCH_URL,
                "categoria_amorel": category,
                "fecha_amorel": published_at,
                "imagenes_detectadas": image_urls,
            },
            ensure_ascii=False,
        ),
        "coordenadas": None,
        "latitud": None,
        "longitud": None,
        "direccion": direccion,
        "ciudad": ciudad,
        "barrio": barrio,
        "tipo_inmueble": tipo_inmueble,
        "ph": None,
        "estrato": extract_count(description, [r"ESTRATO\s+(\d+)"]),
        "descripcion": description,
        "precio": price,
        "m2": extract_area(description),
        "m2_construido": None,
        "antiguedad": None,
        "pisos": extract_count(description, [r"(\d+)\s+PISOS?", r"PISO\s+(\d+)"]),
        "habitaciones": extract_count(description, [r"(\d+)\s+HABITACI\S*", r"(\d+)\s+ALCOBAS?"]),
        "banios": extract_count(description, [r"(\d+)\s+BA\S*OS?", r"(\d+)\s+BA\S*O"]),
        "parqueadero": 1 if re.search(r"\b(GARAJE|PARQUEADERO)\b", normalize_text(description)) else None,
        "administracion": None,
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


def save_html(html, codigo_archivo, publicacion_id):
    html_dir, _ = get_publication_evidence_dirs(publicacion_id)
    path = html_dir / f"amorel_{sanitize_filename(codigo_archivo)}.html"
    with open(path, "w", encoding="utf-8") as file:
        file.write(html)
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
    print("[INFO] Iniciando scraper Amorel Pasto")
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
    total_errores = 0

    for index, link in enumerate(publication_links, start=1):
        print(f"\n[INFO] Procesando Amorel {index}/{len(publication_links)}")
        print(f"[INFO] Link: {link}")
        try:
            data, html, image_urls, skip_reason = extract_publication_data(link)
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
                html_path = save_html(html, data.get("codigo_externo"), publicacion_existente_id)
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
                    print(f"[SKIP] Ya existia al momento de insertar. ID {publicacion_existente_id}")
                    continue
                raise

            total_nuevas += 1
            codigo_archivo = data.get("codigo_externo") or f"publicacion_{publicacion_id}"
            html_path = save_html(html, codigo_archivo, publicacion_id)
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
