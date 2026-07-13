import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from mysql.connector import IntegrityError
try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None

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

BASE_URL = "https://www.facebook.com"
SOURCE_NAME = "Facebook Marketplace"
DB_CONFIG = get_db_config()
EVIDENCE_PREFIX = "facebook"
get_connection = partial(core_get_connection, db_config=DB_CONFIG)
get_or_create_fuente_id = partial(
    core_get_or_create_fuente_id,
    nombre="Facebook Marketplace",
    url_base="https://www.facebook.com/marketplace/",
    tipo_fuente="marketplace",
    descripcion="Scraper de inmuebles en venta en Pasto desde Facebook Marketplace.",
)
save_html = partial(core_save_html, prefix=EVIDENCE_PREFIX)

DEFAULT_SEARCH_PHRASES = [
    "venta casa pasto",
    "vendo casa pasto",
    "casa en venta pasto",
    "venta apartamento pasto",
    "apartamento en venta pasto",
    "vendo apartamento pasto",
    "venta lote pasto",
    "lote en venta pasto",
    "venta oficina pasto",
    "venta local pasto",
    "venta finca pasto",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Facebook usa su propia opcion y corre oculto por defecto. De esta forma un
# HEADLESS=false global no abre una ventana de Chromium durante el scraping.
HEADLESS = os.getenv("FACEBOOK_HEADLESS", "true").strip().lower() in ("1", "true", "yes", "y")
DRY_RUN = os.getenv("FACEBOOK_DRY_RUN", "false").lower() in ("1", "true", "yes", "y")
SEARCH_CITY = os.getenv("FACEBOOK_SEARCH_CITY", "pasto")
SEARCH_CATEGORY = os.getenv("FACEBOOK_SEARCH_CATEGORY", "homesales")
SEARCH_RADIUS = os.getenv("FACEBOOK_SEARCH_RADIUS")
DATE_LISTED_DAYS = os.getenv("FACEBOOK_DATE_LISTED_DAYS")
MIN_PRICE_FILTER = os.getenv("FACEBOOK_MIN_PRICE")
MAX_PRICE_FILTER = os.getenv("FACEBOOK_MAX_PRICE")
MIN_SALE_PRICE = int(os.getenv("FACEBOOK_MIN_SALE_PRICE", "10000000"))
MAX_SCROLLS = int(os.getenv("FACEBOOK_MAX_SCROLLS", "0"))
STALL_SCROLLS = int(os.getenv("FACEBOOK_STALL_SCROLLS", "4"))
MAX_LINKS = int(os.getenv("FACEBOOK_MAX_LINKS", "0"))
MAX_DETAILS = int(os.getenv("FACEBOOK_MAX_DETAILS", "0"))
MAX_IMAGES_PER_LISTING = int(os.getenv("FACEBOOK_MAX_IMAGES_PER_LISTING", "12"))
SCROLL_PAUSE_SECONDS = float(os.getenv("FACEBOOK_SCROLL_PAUSE_SECONDS", "2.5"))
REQUEST_PAUSE_SECONDS = float(os.getenv("REQUEST_PAUSE_SECONDS", "1.0"))
LOGIN_WAIT_SECONDS = int(os.getenv("FACEBOOK_LOGIN_WAIT_SECONDS", "90"))
PAGE_TIMEOUT_MS = int(os.getenv("FACEBOOK_PAGE_TIMEOUT_MS", "45000"))
PROFILE_DIR = Path(os.getenv("FACEBOOK_USER_DATA_DIR", ".facebook_profile"))
EVIDENCE_DIR = Path("evidencias")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = Path("logs")

NEGATIVE_OPERATION_PATTERNS = [
    r"\bARRIEND(?:O|A|AN|E|EN|AS|OS|AR)\b",
    r"\bARREND(?:O|A|AN|E|EN|AS|OS|AR)\b",
    r"\bALQUIL(?:O|A|AN|E|ER|ERES|AR)\b",
    r"\bRENTA\b",
    r"\bRENTO\b",
    r"\bANTICRES(?:IS|O|A)?\b",
    r"\bPERMUT(?:O|A|AN|AR)\b",
    r"\bBUSC(?:O|A|AN|AR)\b",
    r"\bCOMPR(?:O|A|AN|AR)\b",
]

SALE_PATTERNS = [
    r"\bSE\s+VENDE\b",
    r"\bEN\s+VENTA\b",
    r"\bVENTA\b",
    r"\bVENDO\b",
    r"\bVENDE\b",
    r"\bVENDER\b",
]

PROPERTY_TYPES = [
    ("Apartaestudio", ["APARTAESTUDIO", "APARTA ESTUDIO"]),
    ("Apartamento", ["APARTAMENTO", "APARTAMENTOS", "APTO", "APARTA-MENTO"]),
    ("Casa", ["CASA", "CASAS"]),
    ("Oficina", ["OFICINA", "OFICINAS"]),
    ("Local", ["LOCAL", "LOCALES"]),
    ("Bodega", ["BODEGA", "BODEGAS"]),
    ("Lote", ["LOTE", "LOTES", "TERRENO", "PARCELA"]),
    ("Finca", ["FINCA", "FINCAS"]),
    ("Edificio", ["EDIFICIO"]),
]

OUT_OF_CITY_KEYWORDS = [
    "CHACHAGUI",
    "BUESACO",
    "IPIALES",
    "TUQUERRES",
    "TUMACO",
    "LA UNION",
    "SANDONA",
    "CONSACA",
    "YACUANQUER",
    "TANGUA",
    "NARINO, NARINO",
]

UI_TITLE_REJECTS = {
    "FACEBOOK",
    "MARKETPLACE",
    "NOTIFICACIONES",
    "INICIO",
    "MENU",
    "MENSAJES",
    "TU CUENTA",
    "CREAR PUBLICACION",
}

UI_LINE_EXACT_REJECTS = {
    "INICIAR SESION",
    "OLVIDASTE LA CUENTA?",
    "OLVIDASTE TU CUENTA?",
    "MARKETPLACE",
    "EXPLORAR TODO",
    "TU CUENTA",
    "CREAR PUBLICACION",
    "UBICACION",
    "CATEGORIAS",
    "VEHICULOS",
    "ALQUILER DE PROPIEDADES",
    "ARTICULOS DEPORTIVOS",
    "ARTICULOS GRATUITOS",
    "ARTICULOS PARA EL HOGAR",
    "CLASIFICADOS",
    "ELECTRONICA",
    "ENTRETENIMIENTO",
    "FAMILIA",
    "INDUMENTARIA",
    "INSTRUMENTOS MUSICALES",
    "JARDIN Y AIRE LIBRE",
    "JUGUETES Y JUEGOS",
    "MATERIALES PARA REFORMAS EN EL HOGAR",
    "PASATIEMPOS",
    "PRODUCTOS PARA MASCOTAS",
    "SUMINISTROS DE OFICINA",
    "VIVIENDAS EN VENTA",
    "MAS CATEGORIAS",
    "CIUDADES CERCA",
    "VER MAS",
    "VER M.S",
    "ENVIAR MENSAJE",
    "GUARDAR",
    "COMPARTIR",
    "DISPONIBLE",
    "NOTIFICACIONES",
}

LISTING_STOP_MARKERS = [
    "INFORMACION DEL VENDEDOR",
    "DETALLES DEL VENDEDOR",
    "SELLER INFORMATION",
    "SELLER DETAILS",
    "PUBLICACIONES RELACIONADAS",
    "RELATED LISTINGS",
    "MAS PUBLICACIONES DEL VENDEDOR",
    "MORE FROM THIS SELLER",
]

def split_env_list(value):
    if not value:
        return []
    parts = re.split(r"[\n;|]+", value)
    return [part.strip() for part in parts if part.strip()]

def normalize_text(value):
    value = clean_text(value) or ""
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.upper()

def get_lines(text):
    lines = []
    for raw_line in (text or "").splitlines():
        line = clean_text(raw_line)
        if line:
            lines.append(line)
    return lines

def get_search_phrases():
    return split_env_list(os.getenv("FACEBOOK_SEARCH_PHRASES")) or DEFAULT_SEARCH_PHRASES

def build_search_urls():
    configured_urls = split_env_list(os.getenv("FACEBOOK_MARKETPLACE_URLS"))
    if configured_urls:
        return configured_urls

    urls = []
    for phrase in get_search_phrases():
        params = {"query": phrase}
        if SEARCH_CATEGORY:
            params["category"] = SEARCH_CATEGORY
        if SEARCH_RADIUS:
            params["radius"] = SEARCH_RADIUS
        if DATE_LISTED_DAYS:
            params["daysSinceListed"] = DATE_LISTED_DAYS
        if MIN_PRICE_FILTER:
            params["minPrice"] = MIN_PRICE_FILTER
        if MAX_PRICE_FILTER:
            params["maxPrice"] = MAX_PRICE_FILTER
        params["sortBy"] = "creation_time_descend"
        urls.append(f"{BASE_URL}/marketplace/{quote_plus(SEARCH_CITY)}/search/?{urlencode(params)}")
    return urls

def normalize_marketplace_link(raw_url):
    if not raw_url:
        return None
    full_url = urljoin(BASE_URL, raw_url)
    match = re.search(r"/marketplace/item/(\d+)", urlsplit(full_url).path)
    if not match:
        return None
    return f"{BASE_URL}/marketplace/item/{match.group(1)}/"

def extract_marketplace_id(url):
    match = re.search(r"/marketplace/item/(\d+)", url or "")
    return match.group(1) if match else None

def create_audit(search_urls):
    search_url = " | ".join(search_urls[:5])
    if len(search_urls) > 5:
        search_url += f" | +{len(search_urls) - 5} busquedas"
    return ScraperAudit(SOURCE_NAME, search_url=search_url)

def goto_page(page, url, wait_until="domcontentloaded"):
    page.goto(url, wait_until=wait_until, timeout=PAGE_TIMEOUT_MS)
    page.wait_for_timeout(1200)

def click_cookie_buttons(page):
    names = [
        "Permitir todas las cookies",
        "Aceptar todas",
        "Aceptar todo",
        "Allow all cookies",
        "Accept all",
    ]
    for name in names:
        try:
            button = page.get_by_role("button", name=re.compile(name, re.IGNORECASE))
            if button.count() > 0 and button.first.is_visible(timeout=1000):
                button.first.click(timeout=2000)
                page.wait_for_timeout(800)
                return
        except Exception:
            continue

def page_needs_login_or_checkpoint(page):
    current_url = page.url.lower()
    if "/login" in current_url or "/checkpoint" in current_url:
        return True
    try:
        body = normalize_text(page.locator("body").inner_text(timeout=4000))
    except Exception:
        body = ""
    markers = [
        "INICIA SESION",
        "INICIAR SESION",
        "LOG IN TO FACEBOOK",
        "LOGIN TO FACEBOOK",
        "CHECKPOINT",
        "CAPTCHA",
    ]
    return any(marker in body for marker in markers)

def wait_for_manual_login_if_needed(page):
    if not page_needs_login_or_checkpoint(page):
        return
    if HEADLESS:
        print("[WARN] Facebook pide login/checkpoint y FACEBOOK_HEADLESS=true impide resolverlo.")
        return
    print("[WARN] Facebook pide login, 2FA o captcha.")
    print(f"[WARN] Usa la ventana de Chromium para iniciar sesion. Esperando {LOGIN_WAIT_SECONDS}s...")
    page.wait_for_timeout(LOGIN_WAIT_SECONDS * 1000)

def extract_links_from_page(page):
    try:
        hrefs = page.eval_on_selector_all(
            'a[href*="/marketplace/item/"]',
            "(elements) => elements.map((element) => element.href || element.getAttribute('href'))",
        )
    except Exception:
        hrefs = []

    links = []
    seen = set()
    for href in hrefs:
        link = normalize_marketplace_link(href)
        if not link or link in seen:
            continue
        seen.add(link)
        links.append(link)
    return links

def collect_publication_links(context):
    search_urls = build_search_urls()
    audit = create_audit(search_urls)
    audit.set_listing_summary(
        total_reported=None,
        pages_expected=None,
        pages_planned=len(search_urls) * MAX_SCROLLS if MAX_SCROLLS > 0 else None,
        page_size=None,
        limit_reason=None,
    )

    page = context.new_page()
    all_links = []
    seen = set()
    limit_reason = None

    for query_index, search_url in enumerate(search_urls, start=1):
        print(f"\n[INFO] Busqueda Facebook {query_index}/{len(search_urls)}")
        print(f"[INFO] URL: {search_url}")
        try:
            goto_page(page, search_url)
            click_cookie_buttons(page)
            wait_for_manual_login_if_needed(page)
        except Exception as error:
            reason = f"No se pudo abrir busqueda: {error}"
            print(f"[WARN] {reason}")
            audit.record_page(f"q{query_index}", url=search_url, status="error", reason=reason)
            continue

        if page_needs_login_or_checkpoint(page):
            reason = "Facebook sigue pidiendo login/checkpoint; no hay resultados visibles."
            print(f"[WARN] {reason}")
            audit.record_page(f"q{query_index}", url=search_url, status="error", reason=reason)
            continue

        stall_count = 0
        scroll_number = 0
        while MAX_SCROLLS == 0 or scroll_number < MAX_SCROLLS:
            scroll_number += 1
            page.wait_for_timeout(int(SCROLL_PAUSE_SECONDS * 1000))
            page_links = extract_links_from_page(page)
            new_links = 0
            duplicate_links = 0

            for link in page_links:
                item_id = extract_marketplace_id(link) or link
                if item_id in seen:
                    duplicate_links += 1
                    continue
                seen.add(item_id)
                all_links.append(link)
                new_links += 1

                if MAX_LINKS > 0 and len(all_links) >= MAX_LINKS:
                    limit_reason = f"FACEBOOK_MAX_LINKS={MAX_LINKS} limito la busqueda."
                    break

            audit.record_page(
                f"q{query_index}_scroll_{scroll_number}",
                url=search_url,
                links_count=len(page_links),
                new_links_count=new_links,
                duplicate_links_count=duplicate_links,
            )
            scroll_progress = f"{scroll_number}/{MAX_SCROLLS}" if MAX_SCROLLS > 0 else str(scroll_number)
            print(
                f"[INFO] Scroll {scroll_progress}: "
                f"{len(page_links)} links visibles, {new_links} nuevos, {duplicate_links} repetidos"
            )

            if limit_reason:
                break

            if new_links == 0:
                stall_count += 1
            else:
                stall_count = 0

            if stall_count >= STALL_SCROLLS:
                audit.add_note(
                    f"Busqueda {query_index} detenida: {STALL_SCROLLS} scrolls seguidos sin links nuevos."
                )
                break

            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.mouse.wheel(0, 2500)
            except Exception:
                pass

        if limit_reason:
            break

    page.close()
    if limit_reason:
        audit.limit_reason = limit_reason
    if not all_links:
        audit.add_note(
            "No se detectaron links /marketplace/item/. Causas probables: login, captcha, "
            "Marketplace sin resultados visibles o cambio de HTML."
        )
    return all_links, audit

def click_see_more_buttons(page):
    labels = [
        "Ver mas",
        "Ver mas detalles",
        "Ver m.s",
        "See more",
        "Mostrar mas",
        "Mostrar m.s",
    ]
    for label in labels:
        try:
            locator = page.get_by_role("button", name=re.compile(label, re.IGNORECASE))
            count = min(locator.count(), 4)
            for index in range(count):
                try:
                    locator.nth(index).click(timeout=1500)
                    page.wait_for_timeout(400)
                except Exception:
                    continue
        except Exception:
            continue

def safe_body_text(page):
    try:
        return page.locator("body").inner_text(timeout=10000)
    except Exception:
        return ""

def meta_content(page, selector):
    try:
        if page.locator(selector).count() == 0:
            return None
        return clean_text(page.locator(selector).first.get_attribute("content", timeout=1000))
    except Exception:
        return None

def extract_title(page, body_text):
    candidates = []
    try:
        page_title = page.title()
        page_title = re.sub(r"^\(\d+\)\s*", "", page_title or "")
        page_title = re.sub(r"\s*\|\s*Facebook\s*$", "", page_title)
        page_title = re.sub(r"^Marketplace\s*-\s*", "", page_title)
        if page_title:
            candidates.append(page_title)
    except Exception:
        pass

    for selector in ['meta[property="og:title"]', 'meta[name="twitter:title"]']:
        value = meta_content(page, selector)
        if value:
            candidates.append(value)

    try:
        candidates.extend(page.locator("h1").all_inner_texts())
    except Exception:
        pass

    lines = get_lines(body_text)
    for line in lines:
        norm = normalize_text(line)
        has_sale_word = any(re.search(pattern, norm) for pattern in SALE_PATTERNS)
        has_property_word = any(keyword in norm for _, keywords in PROPERTY_TYPES for keyword in keywords)
        if has_sale_word and has_property_word:
            candidates.append(line)
        elif has_sale_word and 8 <= len(line) <= 180:
            candidates.append(line)

    for candidate in candidates:
        value = clean_text(candidate)
        if not value:
            continue
        norm = normalize_text(value)
        if norm in UI_TITLE_REJECTS or "FACEBOOK MARKETPLACE" in norm:
            continue
        if 4 <= len(value) <= 220:
            return value
    return None

def decode_facebook_string(value):
    if value is None:
        return None
    try:
        return clean_text(json.loads(f'"{value}"'))
    except Exception:
        value = value.replace("\\/", "/")
        try:
            return clean_text(bytes(value, "utf-8").decode("unicode_escape"))
        except Exception:
            return clean_text(value)

def extract_first_json_string(html, patterns):
    for pattern in patterns:
        match = re.search(pattern, html or "")
        if match:
            return decode_facebook_string(match.group(1))
    return None

def extract_embedded_listing_fields(html):
    title = extract_first_json_string(
        html,
        [
            r'"base_marketplace_listing_title"\s*:\s*"((?:\\.|[^"\\])*)"',
            r'"marketplace_listing_title"\s*:\s*"((?:\\.|[^"\\])*)"',
        ],
    )
    description = extract_first_json_string(
        html,
        [
            r'"redacted_description"\s*:\s*\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"',
            r'"description"\s*:\s*\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"',
        ],
    )
    price_text = extract_first_json_string(
        html,
        [
            r'"formatted_price"\s*:\s*\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"',
            r'"formatted_amount_zeros_stripped"\s*:\s*"((?:\\.|[^"\\])*)"',
        ],
    )
    location = extract_first_json_string(
        html,
        [r'"location_text"\s*:\s*\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"'],
    )

    price_amount = None
    match = re.search(r'"listing_price"\s*:\s*\{[^{}]*"amount"\s*:\s*"(\d+)"', html or "")
    if match:
        try:
            price_amount = int(match.group(1))
        except ValueError:
            price_amount = None

    return {
        "title": title,
        "description": description,
        "price_text": price_text,
        "price_amount": price_amount,
        "location": location,
    }

def is_ui_noise_line(line):
    norm = normalize_text(line)
    if not norm:
        return True
    if norm in UI_LINE_EXACT_REJECTS:
        return True
    if re.fullmatch(r"[.\s]*", norm):
        return True
    if re.fullmatch(r"EN UN RADIO DE\s+\d+\s+KM", norm):
        return True
    if re.fullmatch(r"\$?\s*0", norm):
        return True
    return False

def is_price_like_line(line):
    norm = normalize_text(line)
    return bool(
        re.search(r"\$\s*[0-9]", norm)
        or re.search(r"\b[0-9]{2,4}\s*(MILLONES|MILLON|MM)\b", norm)
        or re.search(r"\b(PRECIO|VALOR)\b", norm)
    )

def find_listing_start(lines, title):
    title_norm = normalize_text(title)
    if title_norm:
        for index, line in enumerate(lines):
            line_norm = normalize_text(line)
            if line_norm == title_norm or title_norm in line_norm:
                return index

    for index, line in enumerate(lines):
        norm = normalize_text(line)
        has_sale_word = any(re.search(pattern, norm) for pattern in SALE_PATTERNS)
        has_property_word = any(keyword in norm for _, keywords in PROPERTY_TYPES for keyword in keywords)
        if has_sale_word and has_property_word:
            return index

    for index, line in enumerate(lines):
        if not is_price_like_line(line):
            continue
        for offset in range(1, 8):
            candidate_index = index - offset
            if candidate_index < 0:
                break
            candidate = lines[candidate_index]
            candidate_norm = normalize_text(candidate)
            if is_ui_noise_line(candidate):
                continue
            if len(candidate) >= 6 and candidate_norm not in UI_TITLE_REJECTS:
                return candidate_index
    return None

def extract_listing_lines(body_text, title):
    lines = get_lines(body_text)
    if not lines:
        return []

    start = find_listing_start(lines, title)
    if start is None:
        return []

    selected = []
    for line in lines[start:]:
        norm = normalize_text(line)
        if selected and any(marker in norm for marker in LISTING_STOP_MARKERS):
            break
        if is_ui_noise_line(line):
            continue
        selected.append(line)
        if len("\n".join(selected)) > 6000:
            break
        if len(selected) >= 140:
            break

    return selected

def extract_description(body_text, title, listing_lines=None):
    lines = listing_lines if listing_lines is not None else extract_listing_lines(body_text, title)
    if not lines:
        return None

    start_markers = [
        "DESCRIPCION DEL VENDEDOR",
        "DESCRIPCION",
        "DESCRIPTION",
        "SELLER'S DESCRIPTION",
        "DETALLES",
        "DETAILS",
    ]

    start = None
    for index, line in enumerate(lines):
        norm = normalize_text(line)
        if any(marker in norm for marker in start_markers):
            start = index + 1
            break
    if start is None:
        start = 0

    selected = []
    for line in lines[start:]:
        if title and normalize_text(line) == normalize_text(title):
            continue
        if is_ui_noise_line(line):
            continue
        selected.append(line)
        if len(" ".join(selected)) > 4000:
            break

    return clean_text("\n".join(selected)) or clean_text("\n".join(lines))

def parse_money_digits(raw):
    digits = re.sub(r"[^\d]", "", raw or "")
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None

def extract_price(text):
    source = text or ""
    core_price = core_parse_price(source)
    if core_price and core_price >= MIN_SALE_PRICE:
        return core_price

    candidates = []

    money_patterns = [
        r"\$\s*([0-9]{1,3}(?:[\.\,\s][0-9]{3}){1,4})",
        r"(?:PRECIO|VALOR)\s*[:\-]?\s*\$?\s*([0-9][0-9\.\,\s]{6,})",
        r"\b([0-9]{8,12})\b",
    ]
    for pattern in money_patterns:
        for match in re.finditer(pattern, normalize_text(source)):
            value = parse_money_digits(match.group(1))
            if value and value >= MIN_SALE_PRICE:
                candidates.append(value)

    million_pattern = r"\b([0-9]{2,4}(?:[\.,][0-9]{1,2})?)\s*(?:MILLONES|MILLON|MM)\b"
    for match in re.finditer(million_pattern, normalize_text(source)):
        number = match.group(1).replace(",", ".")
        try:
            value = int(float(number) * 1_000_000)
        except ValueError:
            continue
        if value >= MIN_SALE_PRICE:
            candidates.append(value)

    return max(candidates) if candidates else None

def has_negative_operation(text):
    source = normalize_text(text)
    for pattern in NEGATIVE_OPERATION_PATTERNS:
        for match in re.finditer(pattern, source):
            prefix = source[max(0, match.start() - 8):match.start()]
            if re.search(r"\bNO\s*(SE\s*)?$", prefix):
                continue
            return True
    return False

def is_sale_listing(title, description):
    source = normalize_text(f"{title or ''}\n{description or ''}")
    core_ok, core_reason = core_sale_status(source)
    if not core_ok and core_reason == "no_venta":
        return False, "no_es_venta_pura"
    if core_ok:
        return True, None

    if has_negative_operation(source):
        return False, "no_es_venta_pura"
    if any(re.search(pattern, source) for pattern in SALE_PATTERNS):
        return True, None
    return False, "sin_palabra_venta"

def extract_property_type(title, description):
    source = normalize_text(f"{title or ''}\n{description or ''}")
    for label, keywords in PROPERTY_TYPES:
        if any(keyword in source for keyword in keywords):
            return label
    return None

def extract_barrio(title, description):
    core_barrio = core_extract_barrio(f"{title or ''}\n{description or ''}")
    if core_barrio:
        return core_barrio

    patterns = [
        r"\bBARRIO\s+([A-Z0-9 \-]+)",
        r"\bSECTOR\s+([A-Z0-9 \-]+)",
        r"\bB\/\s*([A-Z0-9 \-]+)",
    ]
    source_lines = f"{title or ''}\n{description or ''}".splitlines()
    for raw_line in source_lines:
        source = normalize_text(raw_line)
        for pattern in patterns:
            match = re.search(pattern, source)
            if not match:
                continue
            value = re.split(
                r"\b(PASTO|NARINO|CONJUNTO|EDIFICIO|VENTA|VENDE|VENDO|CONSTA|UBICAD[OA])\b",
                match.group(1),
            )[0]
            value = clean_text(value)
            if value:
                return value.title()
    return core_parse_area(text)

def is_explicitly_out_of_city(title, description):
    source = normalize_text(f"{title or ''}\n{description or ''}")
    if "PASTO" in source:
        return False
    return any(keyword in source for keyword in OUT_OF_CITY_KEYWORDS)

def extract_city(title, description):
    source = normalize_text(f"{title or ''}\n{description or ''}")
    if "PASTO" in source:
        return "Pasto"
    return "Pasto"

def extract_area(text):
    source = normalize_text(text)
    patterns = [
        r"(?:AREA|.REA)\s+(?:DEL\s+LOTE\s+)?(?:DE\s+)?([0-9]+(?:[\.,][0-9]+)?)\s*(?:M2|MTS|METROS)",
        r"([0-9]+(?:[\.,][0-9]+)?)\s*(?:M2|MTS|METROS\s+CUADRADOS)",
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
    source = normalize_text(text)
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None

def extract_location(body_text):
    lines = get_lines(body_text)
    for line in lines:
        norm = normalize_text(line)
        if "PASTO" in norm and ("NARINO" in norm or "NARI" in norm):
            return clean_text(line)
    for line in lines:
        if "Pasto" in line:
            return clean_text(line)
    return None

def extract_seller(page, body_text):
    selectors = [
        'a[href*="/marketplace/profile/"]',
        'a[href*="/profile.php"]',
        'a[href*="/people/"]',
    ]
    for selector in selectors:
        try:
            values = page.locator(selector).all_inner_texts()
        except Exception:
            values = []
        for value in values:
            value = clean_text(value)
            if value and len(value) > 2 and "Marketplace" not in value:
                return value[:150]

    lines = get_lines(body_text)
    for index, line in enumerate(lines):
        if normalize_text(line) in ("INFORMACION DEL VENDEDOR", "SELLER INFORMATION"):
            if index + 1 < len(lines):
                return clean_text(lines[index + 1])[:150]
    return None

def extract_image_urls(page):
    try:
        images = page.evaluate(
            """
            () => Array.from(document.images).map((img) => ({
                src: img.currentSrc || img.src || '',
                width: img.naturalWidth || img.width || 0,
                height: img.naturalHeight || img.height || 0,
                alt: img.alt || ''
            }))
            """
        )
    except Exception:
        images = []

    image_urls = []
    seen = set()
    for image in images:
        src = image.get("src") or ""
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
        if not src or src in seen:
            continue
        if "static.xx.fbcdn.net" in src or "emoji.php" in src or "rsrc.php" in src:
            continue
        if "fbcdn.net" not in src and "scontent" not in src:
            continue
        if width < 120 or height < 120:
            continue
        seen.add(src)
        image_urls.append(src)
        if len(image_urls) >= MAX_IMAGES_PER_LISTING:
            break
    return image_urls

def extract_publication_data(page, link):
    print(f"[INFO] Extrayendo publicacion Facebook: {link}")
    try:
        goto_page(page, link)
        wait_for_manual_login_if_needed(page)
        click_see_more_buttons(page)
    except Exception as error:
        raise RuntimeError(f"No se pudo abrir publicacion: {error}") from error

    body_text = safe_body_text(page)
    html = page.content()
    embedded = extract_embedded_listing_fields(html)
    title = embedded.get("title") or extract_title(page, body_text)
    embedded_text = "\n".join(
        value
        for value in [
            embedded.get("title"),
            embedded.get("price_text"),
            embedded.get("location"),
            embedded.get("description"),
        ]
        if value
    )
    content_source = "\n".join(value for value in [body_text, embedded_text] if value)
    listing_lines = extract_listing_lines(content_source, title)
    if not listing_lines:
        if page_needs_login_or_checkpoint(page):
            return None, html, [], "login_o_checkpoint"
        return None, html, [], "sin_contenido_publicacion"

    listing_text = clean_text("\n".join(listing_lines)) or ""
    description = extract_description(body_text, title, listing_lines)
    full_text = "\n".join([title or "", description or "", listing_text])

    sale_ok, sale_reason = is_sale_listing(title, full_text)
    if not sale_ok:
        print(f"[SKIP] No es venta pura: {title} ({sale_reason})")
        return None, html, [], sale_reason

    price = extract_price(full_text) or embedded.get("price_amount")
    if not price:
        print(f"[SKIP] Venta sin precio real: {title}")
        return None, html, [], "sin_precio"

    tipo_inmueble = extract_property_type(title, full_text)

    if is_explicitly_out_of_city(title, full_text):
        print(f"[SKIP] Publicacion parece estar fuera de Pasto: {title}")
        return None, html, [], "fuera_de_pasto"

    item_id = extract_marketplace_id(link)
    barrio = extract_barrio(title, full_text)
    if not barrio:
        print(f"[SKIP] Venta con precio pero sin barrio identificable: {title}")
        return None, html, [], "sin_barrio"

    ciudad = extract_city(title, full_text)
    location = embedded.get("location") or extract_location(listing_text) or extract_location(body_text)
    image_urls = extract_image_urls(page)
    seller = extract_seller(page, body_text)
    ph = core_detect_ph(full_text)

    notes = {
        "titulo_facebook": title,
        "ubicacion_facebook": location,
        "vendedor_facebook": seller,
        "imagenes_detectadas": image_urls,
        "min_sale_price": MIN_SALE_PRICE,
        "contenido_filtrado": listing_text[:3000],
    }
    data = {
        "codigo_externo": f"FB {item_id}" if item_id else None,
        "link_origen": normalize_marketplace_link(link) or link,
        "links_adicionales": json.dumps(notes, ensure_ascii=False),
        "coordenadas": None,
        "latitud": None,
        "longitud": None,
        "direccion": clean_text(", ".join(value for value in [barrio, ciudad, "Narino"] if value)),
        "ciudad": ciudad,
        "barrio": barrio,
        "tipo_inmueble": tipo_inmueble,
        "ph": ph,
        "estrato": extract_count(full_text, [r"ESTRATO\s+([0-9])"]),
        "descripcion": description,
        "precio": price,
        "m2": extract_area(full_text),
        "m2_construido": None,
        "antiguedad": None,
        "pisos": extract_count(full_text, [r"([0-9]+)\s+PISOS?", r"PISO\s+([0-9]+)"]),
        "habitaciones": extract_count(
            full_text,
            [r"([0-9]+)\s+HABITACI\S*", r"([0-9]+)\s+ALCOBAS?", r"([0-9]+)\s+CUARTOS?"],
        ),
        "banios": extract_count(full_text, [r"([0-9]+)\s+BA\S*OS?", r"([0-9]+)\s+BATH"]),
        "parqueadero": 1 if re.search(r"\b(GARAJE|PARQUEADERO|PARKING)\b", normalize_text(full_text)) else None,
        "administracion": None,
        "notas": json.dumps(notes, ensure_ascii=False),
    }
    return data, html, image_urls, None

def save_collected_links(publication_links, audit):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"facebook_marketplace_links_{timestamp}.json"
    payload = {
        "portal": SOURCE_NAME,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "search_url": audit.search_url,
        "total_links": len(publication_links),
        "links": publication_links,
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(f"[AUDITORIA] Links recolectados guardados: {path}")
    return path

def print_db_connection_help(error):
    if "DB_PASSWORD" in os.environ:
        password_status = "definida_en_entorno_o_env"
    elif DB_CONFIG.get("password"):
        password_status = "definida_en_env_local"
    else:
        password_status = "vacia"
    print("[ERROR] No se pudo conectar a MySQL.")
    print(f"[ERROR] Detalle: {error}")
    print(
        "[ERROR] Config usada: "
        f"DB_HOST={DB_CONFIG.get('host')} "
        f"DB_PORT={DB_CONFIG.get('port')} "
        f"DB_USER={DB_CONFIG.get('user')} "
        f"DB_NAME={DB_CONFIG.get('database')} "
        f"DB_PASSWORD: {password_status}"
    )
    if "DB_PASSWORD" not in os.environ:
        print("[ERROR] DB_PASSWORD no vino del entorno de PowerShell; revisa tambien .env.local.")
    print("[ERROR] Soluciones:")
    print("[ERROR] - Define DB_PASSWORD en PowerShell o en .env.local con tu clave real.")
    print("[ERROR] - Revisa el puerto: $env:DB_PORT=\"3306\" o el que use tu MySQL.")
    print("[ERROR] - Para probar sin guardar: $env:FACEBOOK_DRY_RUN=\"true\"")

def download_image_with_context(context, image_url, codigo_archivo, index, publicacion_id):
    _, img_dir = get_publication_evidence_dirs(publicacion_id)
    filename = f"facebook_{sanitize_filename(codigo_archivo)}_{index:02d}.jpg"
    path = img_dir / filename
    try:
        response = context.request.get(image_url, timeout=PAGE_TIMEOUT_MS)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status}")
        content = response.body()
        if not content:
            return None
        with open(path, "wb") as file:
            file.write(content)
        return path
    except Exception as first_error:
        try:
            request = Request(image_url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=15) as response:
                content = response.read()
            if not content:
                return None
            with open(path, "wb") as file:
                file.write(content)
            return path
        except Exception as second_error:
            print(f"[WARN] No se pudo descargar imagen {image_url}: {first_error} / {second_error}")
            return None

def save_publication_evidence(context, connection, publicacion_id, data, html, image_urls):
    codigo_archivo = data.get("codigo_externo") or f"publicacion_{publicacion_id}"
    html_path = save_html(html, codigo_archivo, publicacion_id)
    if connection:
        insert_evidencia(connection, publicacion_id, "html", html_path, data.get("link_origen"))

    print(f"[INFO] Imagenes detectadas: {len(image_urls)}")
    for index, image_url in enumerate(image_urls, start=1):
        image_path = download_image_with_context(context, image_url, codigo_archivo, index, publicacion_id)
        if image_path and connection:
            insert_evidencia(connection, publicacion_id, "imagen", image_path, image_url)

def open_facebook_context(playwright):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=HEADLESS,
        locale="es-CO",
        viewport={"width": 1366, "height": 900},
        user_agent=USER_AGENT,
        args=["--disable-blink-features=AutomationControlled"],
    )

def main():
    if sync_playwright is None:
        raise RuntimeError("playwright no esta instalado. Ejecuta: pip install playwright")

    print("[INFO] Iniciando scraper Facebook Marketplace")
    print("[INFO] Fuente revisada: Facebook Marketplace")
    print(f"[INFO] FACEBOOK_SEARCH_CITY: {SEARCH_CITY}")
    print(f"[INFO] FACEBOOK_HEADLESS: {HEADLESS}")
    print(f"[INFO] FACEBOOK_DRY_RUN: {DRY_RUN}")
    print(f"[INFO] FACEBOOK_MAX_SCROLLS: {MAX_SCROLLS if MAX_SCROLLS > 0 else 'sin limite'}")
    print(f"[INFO] FACEBOOK_MIN_SALE_PRICE: {MIN_SALE_PRICE}")
    print(f"[INFO] Perfil Chromium: {PROFILE_DIR.resolve()}")

    connection = None
    fuente_id = None
    total_nuevas = 0
    total_saltadas = 0
    total_omitidas = 0
    total_sin_precio = 0
    total_no_venta = 0
    total_sin_barrio = 0
    total_errores = 0

    with sync_playwright() as playwright:
        context = open_facebook_context(playwright)
        try:
            publication_links, audit = collect_publication_links(context)
            if MAX_DETAILS > 0:
                audit.add_note(f"FACEBOOK_MAX_DETAILS={MAX_DETAILS} limito el procesamiento de detalles.")
                publication_links = publication_links[:MAX_DETAILS]
            print(f"[INFO] Total links Facebook encontrados: {len(publication_links)}")
            save_collected_links(publication_links, audit)

            if not DRY_RUN:
                try:
                    connection = get_connection()
                    fuente_id = get_or_create_fuente_id(connection)
                except Exception as error:
                    total_errores += 1
                    audit.record_error("mysql", error)
                    print_db_connection_help(error)
                    audit.set_processing_counts(
                        nuevas=total_nuevas,
                        saltadas=total_saltadas,
                        omitidas=total_omitidas,
                        errores=total_errores,
                    )
                    audit.print_summary(len(publication_links))
                    audit.save(len(publication_links))
                    return

            detail_page = context.new_page()
            for index, link in enumerate(publication_links, start=1):
                print(f"\n[INFO] Procesando Facebook {index}/{len(publication_links)}")
                print(f"[INFO] Link: {link}")
                try:
                    data, html, image_urls, skip_reason = extract_publication_data(detail_page, link)
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

                    if DRY_RUN:
                        total_nuevas += 1
                        print(
                            "[DRY_RUN] Aceptada: "
                            f"{data['tipo_inmueble']} | {data['ciudad']} | {data['precio']} | {data['link_origen']}"
                        )
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
                        save_publication_evidence(
                            context,
                            connection,
                            publicacion_existente_id,
                            data,
                            html,
                            image_urls,
                        )
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
                    save_publication_evidence(context, connection, publicacion_id, data, html, image_urls)
                    print(f"[OK] Guardada publicacion Facebook ID {publicacion_id}")
                    print(f"[OK] Codigo externo: {data['codigo_externo']}")
                    print(f"[OK] Tipo: {data['tipo_inmueble']} | Barrio: {data['barrio']} | Ciudad: {data['ciudad']}")
                    print(f"[OK] Precio: {data['precio']} | Area: {data['m2']}")

                    if REQUEST_PAUSE_SECONDS > 0:
                        time.sleep(REQUEST_PAUSE_SECONDS)
                except Exception as error:
                    total_errores += 1
                    audit.record_error(link, error)
                    print(f"[ERROR] Fallo publicacion Facebook {link}: {error}")
            detail_page.close()
        finally:
            context.close()
            if connection:
                connection.close()

    print("\n[OK] Scraping Facebook Marketplace finalizado.")
    print_scraper_summary(
        fuente="Facebook Marketplace",
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
