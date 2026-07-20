import hashlib
import html as html_module
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

try:
    import mysql.connector
    from mysql.connector import IntegrityError
except ImportError:
    mysql = None
    IntegrityError = Exception

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None

from db_config import get_db_config
from duplicate_detector import detect_duplicates_safely
from location_normalizer import location_diagnostic, resolve_pasto_location
from net_retry import with_retry
from scraper_audit import ScraperAudit


load_dotenv()

BASE_URL = "https://www.facebook.com"
SOURCE_NAME = "Facebook Marketplace"

# Facebook corre contra una instancia MySQL en 3301 salvo que se indique otra.
DB_DEFAULT_PORT = "3301"

DEFAULT_MARKETPLACE_URLS = [
    (
        "https://www.facebook.com/marketplace/108037152563666/search/"
        "?category_id=1270772586445798&query=Viviendas%20en%20venta"
        "&referral_ui_component=category_menu_item"
    ),
]

DEFAULT_PRICE_BUCKETS = [
    (None, 80_000_000),
    (80_000_000, 120_000_000),
    (120_000_000, 160_000_000),
    (160_000_000, 200_000_000),
    (200_000_000, 250_000_000),
    (250_000_000, 300_000_000),
    (300_000_000, 350_000_000),
    (350_000_000, 400_000_000),
    (400_000_000, 500_000_000),
    (500_000_000, 650_000_000),
    (650_000_000, 800_000_000),
    (800_000_000, 1_000_000_000),
    (1_000_000_000, 1_500_000_000),
    (1_500_000_000, 2_000_000_000),
    (2_000_000_000, 3_000_000_000),
    (3_000_000_000, None),
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

HEADLESS = os.getenv("FACEBOOK_HEADLESS", "false").lower() in ("1", "true", "yes", "y")
DRY_RUN = os.getenv("FACEBOOK_DRY_RUN", "false").lower() in ("1", "true", "yes", "y")
SEARCH_CITY = os.getenv("FACEBOOK_SEARCH_CITY", "pasto")
SEARCH_CATEGORY = os.getenv("FACEBOOK_SEARCH_CATEGORY", "homesales")
SEARCH_RADIUS = os.getenv("FACEBOOK_SEARCH_RADIUS")
DATE_LISTED_DAYS = os.getenv("FACEBOOK_DATE_LISTED_DAYS")
MIN_PRICE_FILTER = os.getenv("FACEBOOK_MIN_PRICE")
MAX_PRICE_FILTER = os.getenv("FACEBOOK_MAX_PRICE")
MIN_SALE_PRICE = int(os.getenv("FACEBOOK_MIN_SALE_PRICE", "10000000"))
TRUST_SALE_FILTERS = os.getenv("FACEBOOK_TRUST_SALE_FILTERS", "true").lower() in ("1", "true", "yes", "y")
SPLIT_PRICE_BUCKETS = os.getenv("FACEBOOK_SPLIT_PRICE_BUCKETS", "true").lower() in ("1", "true", "yes", "y")
INCLUDE_UNFILTERED_LISTING = os.getenv("FACEBOOK_INCLUDE_UNFILTERED_LISTING", "true").lower() in ("1", "true", "yes", "y")
MAX_SCROLLS = int(os.getenv("FACEBOOK_MAX_SCROLLS", "80"))
STALL_SCROLLS = int(os.getenv("FACEBOOK_STALL_SCROLLS", "4"))
MAX_LINKS = int(os.getenv("FACEBOOK_MAX_LINKS", "0"))
MAX_DETAILS = int(os.getenv("FACEBOOK_MAX_DETAILS", "0"))
MAX_IMAGES_PER_LISTING = int(os.getenv("FACEBOOK_MAX_IMAGES_PER_LISTING", "12"))
SCROLL_PAUSE_SECONDS = float(os.getenv("FACEBOOK_SCROLL_PAUSE_SECONDS", "2.5"))
REQUEST_PAUSE_SECONDS = float(os.getenv("REQUEST_PAUSE_SECONDS", "1.0"))
LOGIN_WAIT_SECONDS = int(os.getenv("FACEBOOK_LOGIN_WAIT_SECONDS", "90"))
PAGE_TIMEOUT_MS = int(os.getenv("FACEBOOK_PAGE_TIMEOUT_MS", "45000"))
PROFILE_DIR = Path(os.getenv("FACEBOOK_USER_DATA_DIR", ".facebook_profile"))
SESSION_COOKIES_PATH = Path(
    os.getenv("FACEBOOK_SESSION_COOKIES_PATH", str(PROFILE_DIR / "session_cookies.json"))
)
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
    "POPAYAN",
    "PITALITO",
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


def parse_price_buckets(value):
    if not value:
        return DEFAULT_PRICE_BUCKETS

    buckets = []
    for part in split_env_list(value):
        match = re.match(r"^\s*([0-9_\.]*)\s*(?:-|:|\.\.)\s*([0-9_\.]*)\s*$", part)
        if not match:
            match = re.match(r"^\s*([0-9_\.]+)\s*\+\s*$", part)
            if match:
                min_raw, max_raw = match.group(1), ""
            else:
                print(f"[WARN] Rango de precio invalido en FACEBOOK_PRICE_BUCKETS: {part}")
                continue
        else:
            min_raw, max_raw = match.group(1), match.group(2)

        def parse_bound(raw):
            cleaned = (raw or "").replace("_", "").replace(".", "").strip()
            return int(cleaned) if cleaned else None

        min_price = parse_bound(min_raw)
        max_price = parse_bound(max_raw)
        if min_price is None and max_price is None:
            continue
        if min_price is not None and max_price is not None and min_price >= max_price:
            print(f"[WARN] Rango de precio omitido porque min >= max: {part}")
            continue
        buckets.append((min_price, max_price))

    return buckets


def set_url_params(url, updates):
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def dedupe_urls(urls):
    deduped = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


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


def get_lines(text):
    lines = []
    for raw_line in (text or "").splitlines():
        line = clean_text(raw_line)
        if line:
            lines.append(line)
    return lines


def get_search_phrases():
    return split_env_list(os.getenv("FACEBOOK_SEARCH_PHRASES"))


def build_search_urls():
    configured_urls = split_env_list(os.getenv("FACEBOOK_MARKETPLACE_URLS"))
    if configured_urls:
        base_urls = configured_urls

    else:
        phrases = get_search_phrases()
        if not phrases:
            base_urls = DEFAULT_MARKETPLACE_URLS
        else:
            urls = []
            for phrase in phrases:
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
            base_urls = urls

    if not SPLIT_PRICE_BUCKETS:
        return dedupe_urls(base_urls)

    urls = []
    for base_url in base_urls:
        if INCLUDE_UNFILTERED_LISTING:
            urls.append(base_url)
        for min_price, max_price in parse_price_buckets(os.getenv("FACEBOOK_PRICE_BUCKETS")):
            updates = {"sortBy": "creation_time_descend"}
            updates["minPrice"] = min_price
            updates["maxPrice"] = max_price
            urls.append(set_url_params(base_url, updates))
    return dedupe_urls(urls)


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
        search_url += f" | +{len(search_urls) - 5} listados"
    return ScraperAudit(SOURCE_NAME, search_url=search_url)


def goto_page(page, url, wait_until="domcontentloaded"):
    with_retry(
        lambda: page.goto(url, wait_until=wait_until, timeout=PAGE_TIMEOUT_MS),
        f"Abrir {url}",
    )
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


def export_session_cookies(context):
    """Guarda las cookies de la sesion activa de Facebook para que el front
    (validador de links) pueda reutilizarlas en lugar de golpear el muro de
    login. Se llama solo cuando ya confirmamos que la sesion esta autenticada,
    asi que nunca persiste un estado "deslogueado" por error."""
    try:
        cookies = [
            cookie for cookie in context.cookies()
            if "facebook.com" in (cookie.get("domain") or "")
        ]
        if not cookies:
            return
        SESSION_COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"exported_at": time.time(), "cookies": cookies}
        with open(SESSION_COOKIES_PATH, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
        print(f"[INFO] Cookies de sesion Facebook exportadas a {SESSION_COOKIES_PATH}")
    except Exception as error:
        print(f"[WARN] No se pudo exportar cookies de sesion: {error}")


def collect_publication_links(context):
    search_urls = build_search_urls()
    audit = create_audit(search_urls)
    audit.set_listing_summary(
        total_reported=None,
        pages_expected=None,
        pages_planned=len(search_urls) * MAX_SCROLLS,
        page_size=None,
        limit_reason=None,
    )

    page = context.new_page()
    all_links = []
    seen = set()
    limit_reason = None

    for query_index, search_url in enumerate(search_urls, start=1):
        print(f"\n[INFO] Listado Facebook {query_index}/{len(search_urls)}")
        print(f"[INFO] URL: {search_url}")
        listing_new_links = 0
        listing_duplicate_links = 0
        try:
            goto_page(page, search_url)
            click_cookie_buttons(page)
            wait_for_manual_login_if_needed(page)
        except Exception as error:
            reason = f"No se pudo abrir listado: {error}"
            print(f"[WARN] {reason}")
            audit.record_page(f"q{query_index}", url=search_url, status="error", reason=reason)
            continue

        if page_needs_login_or_checkpoint(page):
            reason = "Facebook sigue pidiendo login/checkpoint; no hay resultados visibles."
            print(f"[WARN] {reason}")
            audit.record_page(f"q{query_index}", url=search_url, status="error", reason=reason)
            continue

        if query_index == 1:
            export_session_cookies(context)

        stall_count = 0
        for scroll_number in range(1, MAX_SCROLLS + 1):
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
                listing_new_links += 1

                if MAX_LINKS > 0 and len(all_links) >= MAX_LINKS:
                    limit_reason = f"FACEBOOK_MAX_LINKS={MAX_LINKS} limito la recoleccion."
                    break

            listing_duplicate_links += duplicate_links

            audit.record_page(
                f"q{query_index}_scroll_{scroll_number}",
                url=search_url,
                links_count=len(page_links),
                new_links_count=new_links,
                duplicate_links_count=duplicate_links,
            )
            print(
                f"[INFO] Scroll {scroll_number}/{MAX_SCROLLS}: "
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
                    f"Listado {query_index} detenido: {STALL_SCROLLS} scrolls seguidos sin links nuevos."
                )
                break

            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.mouse.wheel(0, 2500)
            except Exception:
                pass

        if limit_reason:
            break

        print(
            f"[INFO] Listado {query_index} terminado: "
            f"{listing_new_links} nuevos, {listing_duplicate_links} repetidos, "
            f"{len(all_links)} acumulados"
        )

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


MAX_REASONABLE_PRICE = 50_000_000_000

PHONE_CONTEXT_PATTERN = re.compile(
    r"\b(TEL\S*|CEL\S*|WHATSAPP|WSP|CONTACTO|LLAMAR|INFORMES?|MOVIL|NUMERO)\b"
)


def _sane_price(value):
    if value and MIN_SALE_PRICE <= value <= MAX_REASONABLE_PRICE:
        return value
    return None


def _has_phone_context_nearby(source, start, end, window=30):
    left = source[max(0, start - window):start]
    right = source[end:end + window]
    return bool(PHONE_CONTEXT_PATTERN.search(left) or PHONE_CONTEXT_PATTERN.search(right))


def _looks_like_phone_number(digits):
    return len(digits) == 10 and digits[0] in "1367"


def parse_marketplace_price_heuristics(text):
    candidates = []
    normalized_source = normalize_text(text)

    unit_pattern = r"\b([0-9]{1,4}(?:[\.,][0-9]{1,3})?)\s*(MILLONES?|MILL\.?|MM|M)\b(?!2)"
    for match in re.finditer(unit_pattern, normalized_source):
        number = match.group(1).replace(",", ".")
        try:
            value = int(round(float(number) * 1_000_000))
        except ValueError:
            continue
        if _sane_price(value):
            candidates.append(value)

    top_lines = get_lines(text)[:6]
    for raw_line in top_lines:
        match = re.fullmatch(r"\$?\s*([0-9]{2,4})", raw_line.strip())
        if not match:
            continue
        number = int(match.group(1))
        if 50 <= number <= 5000:
            candidates.append(number * 1_000_000)

    return candidates


def extract_price(text):
    source = normalize_text(text or "")
    candidates = []

    # Nivel 1 (dentro del texto libre): precio con simbolo $ o precedido de
    # PRECIO/VALOR. Es la forma mas confiable de precio "visible" en el anuncio,
    # por eso se evalua antes que cualquier heuristica de numero suelto.
    explicit_patterns = [
        r"\$\s*([0-9]{1,3}(?:[\.\,\s][0-9]{3}){1,4})",
        r"(?:PRECIO|VALOR)\s*[:\-]?\s*\$?\s*([0-9][0-9\.\,\s]{6,})",
    ]
    for pattern in explicit_patterns:
        for match in re.finditer(pattern, source):
            value = parse_money_digits(match.group(1))
            if _sane_price(value):
                candidates.append(value)
    if candidates:
        return max(candidates)

    # Nivel 2: formatos tipicos de Marketplace en millones (450 millones, 450M, 450MM).
    million_pattern = r"\b([0-9]{2,4}(?:[\.,][0-9]{1,2})?)\s*(?:MILLONES|MILLON|MM)\b"
    for match in re.finditer(million_pattern, source):
        number = match.group(1).replace(",", ".")
        try:
            value = int(float(number) * 1_000_000)
        except ValueError:
            continue
        if _sane_price(value):
            candidates.append(value)

    candidates.extend(v for v in parse_marketplace_price_heuristics(text or "") if _sane_price(v))
    if candidates:
        return max(candidates)

    # Nivel 3 (ultimo recurso): numero suelto de 8-12 digitos sin simbolo de
    # precio cerca. Es el patron mas riesgoso porque puede coincidir con un
    # telefono/whatsapp, asi que se descartan numeros con forma de celular
    # colombiano (10 digitos) y cualquier numero cercano a palabras de contacto.
    for match in re.finditer(r"\b([0-9]{8,12})\b", source):
        digits = match.group(1)
        if _looks_like_phone_number(digits):
            continue
        if _has_phone_context_nearby(source, match.start(), match.end()):
            continue
        value = parse_money_digits(digits)
        if _sane_price(value):
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
    if has_negative_operation(source):
        return False, "no_es_venta_pura"
    if any(re.search(pattern, source) for pattern in SALE_PATTERNS):
        return True, None
    if TRUST_SALE_FILTERS:
        return True, None
    return False, "sin_palabra_venta"


def extract_property_type(title, description):
    source = normalize_text(f"{title or ''}\n{description or ''}")
    for label, keywords in PROPERTY_TYPES:
        if any(keyword in source for keyword in keywords):
            return label
    return None


BARRIO_STRICT_PATTERNS = [
    r"\bBARRIO\s+([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
    r"\bSECTOR\s+([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
    r"\bB\/\s*([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
    r"\bUBICAD[OA]\s+EN\s+(?:EL\s+BARRIO\s+|EL\s+SECTOR\s+)?([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
    r"\bUBICAD[OA]\s+BARRIO\s+([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
    r"\bUBICAD[OA]\s+SECTOR\s+([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
    r"\bEN\s+EL\s+BARRIO\s+([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
    r"\bEN\s+EL\s+SECTOR\s+([A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,3})",
]

BARRIO_LOOSE_PATTERNS = [
    r"\bEN\s+([A-Z][A-Z0-9\-]+(?:\s+[A-Z0-9\-]+){0,2})\b",
]

BARRIO_STOP_WORDS = (
    r"\b(PASTO|NARINO|CONJUNTO|EDIFICIO|VENTA|VENDE|VENDO|VENDER|CONSTA|UBICAD[OA]|EN|"
    r"CERCA|FRENTE|ADMINISTRACION|PRECIO|VALOR|INFORMES|CONTACTO|WHATSAPP|CASA|"
    r"APARTAMENTO|APARTAESTUDIO|LOCAL|BODEGA|LOTE|FINCA|OFICINA|ESTRATO|PISO|PISOS|"
    r"HABITACION\S*|BA\S*OS?|PARQUEADERO\S*|GARAJE\S*|AREA|METROS|MTS|M2)\b"
)

# Palabras que nunca son nombre de barrio: evitan que "en excelente estado",
# "en zona tranquila" o "en conjunto cerrado" se confundan con una ubicacion.
BARRIO_BLOCKLIST = {
    "EXCELENTE", "BUEN", "BUENA", "BUENAS", "BUENOS", "ZONA", "ESTADO", "CONJUNTO",
    "SECTOR", "CENTRICO", "CENTRICA", "TRANQUILO", "TRANQUILA", "VENTA", "ARRIENDO",
    "TODO", "TODA", "ESTE", "ESTA", "GENERAL", "TOTAL", "PLENO", "PLENA",
    "CONDICIONES", "OBRA", "CONSTRUCCION", "PROCESO", "PERFECTO", "PERFECTA",
    "OPTIMO", "OPTIMA", "MUY", "MEJOR", "AMPLIO", "AMPLIA", "BONITO", "BONITA",
}


def _search_barrio_lines(lines, patterns):
    for raw_line in lines:
        source = normalize_text(raw_line)
        for pattern in patterns:
            match = re.search(pattern, source)
            if not match:
                continue
            value = re.split(BARRIO_STOP_WORDS, match.group(1))[0]
            value = clean_text(value)
            if not value:
                continue
            if value.split(" ")[0].upper() in BARRIO_BLOCKLIST:
                continue
            return value.title()
    return None


def extract_barrio(title, description):
    description_lines = (description or "").splitlines()
    title_lines = (title or "").splitlines()

    for lines in (description_lines, title_lines):
        result = _search_barrio_lines(lines, BARRIO_STRICT_PATTERNS)
        if result:
            return result

    for lines in (description_lines, title_lines):
        result = _search_barrio_lines(lines, BARRIO_LOOSE_PATTERNS)
        if result:
            return result

    return None


def extract_declared_city(location_text):
    """Primer segmento del campo de ubicacion que Facebook reporta para el
    anuncio (ej. 'Popayan, Cauca' -> 'POPAYAN'). Es el dato mas confiable sobre
    donde esta publicado realmente el anuncio, mas que el texto libre, que
    frecuentemente menciona 'Pasto' solo como referencia de cercania."""
    if not location_text:
        return None
    first_segment = location_text.split(",")[0]
    return normalize_text(first_segment) or None


def is_explicitly_out_of_city(title, description, location_text=None):
    declared_city = extract_declared_city(location_text)
    if declared_city:
        if declared_city == "PASTO":
            return False
        if any(keyword == declared_city or keyword in declared_city for keyword in OUT_OF_CITY_KEYWORDS):
            return True

    source = normalize_text(f"{title or ''}\n{description or ''}")
    return any(re.search(rf"\b{re.escape(keyword)}\b", source) for keyword in OUT_OF_CITY_KEYWORDS)


def extract_city(title, description):
    source = normalize_text(f"{title or ''}\n{description or ''}")
    if "PASTO" in source:
        return "Pasto"
    return "Pasto"


# ---------------------------------------------------------------------------
# Extraccion de areas (lote / construida / dimensiones del lote)
# ---------------------------------------------------------------------------
# Toda la logica vive en extract_area_details(): un unico punto de entrada
# reutilizable. Nunca se estima ni se inventa un valor: cada campo queda en
# None si el texto no lo dice explicitamente (o, para dimensiones, si el
# contexto no deja claro que se trata del inmueble y no de un mueble/objeto).

_LINEAR_UNIT = r"(?:MTS?|METROS?|M)"
_AREA_UNIT = r"(?:MT2|M2|M\.2|MTS2|MTS\.?|M²|METROS\s+CUADRADOS|METROS\s*2|METROS)"
# Subconjunto sin la palabra suelta "metros": solo unidades que son
# inequivocamente de superficie (evita que "10 metros por 20 metros" se lea
# como area=10 antes de intentar la extraccion de dimensiones).
_AREA_UNIT_STRICT = r"(?:MT2|M2|M\.2|MTS2|MTS\.?|M²|METROS\s+CUADRADOS|METROS\s*2)"
_DIM_SEP = r"(?:X|\*|POR|×)"
_FRENTE_OPT = r"(?:(?:DE\s+)?FRENTE)?"
_FONDO_OPT = r"(?:(?:DE\s+)?FONDO)?"

# Evita que "Lote de 6 x 12" o "Terreno de 10 metros por 20 metros" se lean
# como un area unica (6, o 10) en vez de como un par de dimensiones.
_NEG_DIMENSION_LOOKAHEAD = rf"(?!\s*{_LINEAR_UNIT}?\s*{_DIM_SEP}\s*[0-9])"

BUILT_AREA_KEYWORDS = [
    r"AREA\s+CONSTRUIDA", r"AREA\s+PRIVADA", r"CONSTRUIDOS?", r"CONSTRUCCION", r"CONSTRUIDA",
]
LOT_AREA_KEYWORDS = [
    r"AREA\s+(?:DEL\s+)?LOTE", r"AREA\s+(?:DEL\s+)?TERRENO", r"LOTE", r"TERRENO", r"SOLAR",
]
GENERIC_AREA_KEYWORDS = [
    r"AREA\s+TOTAL", r"METROS\s+CUADRADOS", r"AREA", r"METROS",
]

DIMENSION_PATTERN = (
    rf"([0-9]+(?:[.,][0-9]+)?)\s*{_LINEAR_UNIT}?\s*{_FRENTE_OPT}\s*{_DIM_SEP}\s*"
    rf"([0-9]+(?:[.,][0-9]+)?)\s*{_LINEAR_UNIT}?\s*{_FONDO_OPT}"
)
FRENTE_FONDO_PATTERN = (
    rf"\bFRENTE\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:{_LINEAR_UNIT}\s*)?FONDO\s*[:\-]?\s*"
    rf"([0-9]+(?:[.,][0-9]+)?)\s*{_LINEAR_UNIT}?"
)
BARE_AREA_PATTERN = rf"\b([0-9]+(?:[.,][0-9]+)?)\s*{_AREA_UNIT_STRICT}\b"

# Nunca interpretar estas medidas como area del inmueble (seccion 8 del pedido).
AREA_EXCLUDE_KEYWORDS = {
    "PISCINA", "CLOSET", "CLOSETS", "VENTANA", "VENTANAS", "PUERTA", "PUERTAS",
    "GARAJE", "HABITACION", "HABITACIONES", "PANTALLA", "PANTALLAS", "TELEVISOR",
    "TELEVISORES", "TV", "MUEBLE", "MUEBLES", "ELECTRODOMESTICO", "ELECTRODOMESTICOS",
    "CAMA", "CAMAS",
}
# Palabras que confirman que "N x M" describe el lote/inmueble (HIGH).
AREA_STRONG_KEYWORDS = {"LOTE", "TERRENO", "SOLAR"}
# Palabras que sugieren que "N x M" son medidas del inmueble sin decir "lote" (MEDIUM).
AREA_WEAK_KEYWORDS = {"CASA", "MEDIDAS", "DIMENSIONES", "APARTAMENTO", "APARTAESTUDIO", "INMUEBLE", "PROPIEDAD"}


def _first_keyword_area_match(source, keyword_alternatives):
    keyword_group = "|".join(keyword_alternatives)
    pattern = (
        rf"\b(?:{keyword_group})\s*[:\-]?\s*(?:DE\s+)?"
        rf"([0-9]+(?:[.,][0-9]+)?){_NEG_DIMENSION_LOOKAHEAD}\s*{_AREA_UNIT}?"
    )
    match = re.search(pattern, source)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    if not (5 <= value <= 100_000):
        return None
    return value, match.start(), match.end()


def _first_keyword_area(source, keyword_alternatives):
    found = _first_keyword_area_match(source, keyword_alternatives)
    return found[0] if found else None


def _mask_span(source, start, end):
    """Reemplaza un tramo ya usado por espacios para que un mismo numero no
    se cuente dos veces (ej. que "Area privada: 85 m2" no termine llenando
    built_area_m2 Y lot_area_m2 con el mismo 85)."""
    return source[:start] + (" " * (end - start)) + source[end:]


def _bare_area_value(source):
    for match in re.finditer(BARE_AREA_PATTERN, source):
        pre = source[max(0, match.start() - 40):match.start()]
        if any(re.search(rf"\b{keyword}\b", pre) for keyword in AREA_EXCLUDE_KEYWORDS):
            continue
        try:
            value = float(match.group(1).replace(",", "."))
        except ValueError:
            continue
        if 5 <= value <= 100_000:
            return value
    return None


def _classify_dimension_context(window_text, matched_text):
    if any(re.search(rf"\b{keyword}\b", window_text) for keyword in AREA_EXCLUDE_KEYWORDS):
        return None
    if any(re.search(rf"\b{keyword}\b", window_text) for keyword in AREA_STRONG_KEYWORDS):
        return "HIGH"
    if "FRENTE" in matched_text or "FONDO" in matched_text:
        return "HIGH"
    if any(re.search(rf"\b{keyword}\b", window_text) for keyword in AREA_WEAK_KEYWORDS):
        return "MEDIUM"
    return None


def _best_lot_dimensions(source):
    best = None
    for pattern in (FRENTE_FONDO_PATTERN, DIMENSION_PATTERN):
        for match in re.finditer(pattern, source):
            try:
                num1 = float(match.group(1).replace(",", "."))
                num2 = float(match.group(2).replace(",", "."))
            except ValueError:
                continue
            if not (1 <= num1 <= 500 and 1 <= num2 <= 500):
                continue
            window = source[max(0, match.start() - 40):match.end() + 15]
            confidence = _classify_dimension_context(window, match.group(0))
            if not confidence:
                continue
            rank = 2 if confidence == "HIGH" else 1
            if best is None or rank > best[0]:
                best = (rank, num1, num2, confidence)
    if not best:
        return None
    _, width, length, confidence = best
    return width, length, width * length, confidence


def extract_area_details(text):
    """
    Extrae de forma robusta las areas de un inmueble (lote y/o construida) a
    partir de texto libre de Marketplace. Nunca inventa ni estima: cada campo
    queda en None si el texto no lo dice explicitamente. Devuelve siempre la
    misma estructura, pensada para ser extensible (agregar una palabra clave
    nueva no requiere tocar la logica de resolucion de conflictos).
    """
    result = {
        "lot_width_m": None,
        "lot_length_m": None,
        "lot_area_m2": None,
        "built_area_m2": None,
        "area_source": "unknown",
        "area_confidence": None,
    }
    source = normalize_text(text)
    if not source:
        return result

    confidences = []
    lot_search_source = source

    # 1) Area construida explicita: unica fuente permitida para built_area_m2
    #    (nunca se deriva de habitaciones, pisos, banos, balcones, etc.).
    built_match = _first_keyword_area_match(source, BUILT_AREA_KEYWORDS)
    built_source = None
    if built_match:
        built_value, start, end = built_match
        result["built_area_m2"] = built_value
        built_source = "explicit_built_area"
        confidences.append("HIGH")
        # Se enmascara el tramo ya usado para que el mismo numero no vuelva a
        # contarse como area de lote (ej. "Area privada: 85 m2").
        lot_search_source = _mask_span(source, start, end)

    # 2) Area de lote explicita (con calificativo "lote"/"terreno"/"solar").
    lot_value = _first_keyword_area(lot_search_source, LOT_AREA_KEYWORDS)
    lot_source = "explicit_lot_area" if lot_value is not None else None
    lot_confidence = "HIGH" if lot_value is not None else None

    # 3) Dimensiones del lote (6x12, frente/fondo, etc.), solo si no hubo un
    #    numero de area explicito.
    if lot_value is None:
        dims = _best_lot_dimensions(lot_search_source)
        if dims:
            width, length, area, confidence = dims
            lot_value = area
            result["lot_width_m"] = width
            result["lot_length_m"] = length
            lot_source = "lot_dimensions"
            lot_confidence = confidence

    # 4) Area generica con calificativo debil ("Area:", "Metros:"), como
    #    respaldo antes de rendirse.
    if lot_value is None:
        generic_value = _first_keyword_area(lot_search_source, GENERIC_AREA_KEYWORDS)
        if generic_value is not None:
            lot_value = generic_value
            lot_source = "explicit_lot_area"
            lot_confidence = "HIGH"

    # 5) Ultimo recurso: numero suelto seguido de una unidad de superficie
    #    inequivoca (m2, mts2, m², metros cuadrados), sin ningun calificativo.
    if lot_value is None:
        bare_value = _bare_area_value(lot_search_source)
        if bare_value is not None:
            lot_value = bare_value
            lot_source = "explicit_lot_area"
            lot_confidence = "HIGH"

    if lot_value is not None:
        result["lot_area_m2"] = lot_value
        confidences.append(lot_confidence)

    sources = [item for item in (built_source, lot_source) if item]
    if len(sources) >= 2:
        result["area_source"] = "multiple_sources"
    elif len(sources) == 1:
        result["area_source"] = sources[0]

    if confidences:
        result["area_confidence"] = "MEDIUM" if "MEDIUM" in confidences else "HIGH"

    return result


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


BATHROOM_QUALIFIER_WORDS = ["SOCIAL", "PRINCIPAL", "AUXILIAR", "VISITAS", "SERVICIO"]


def extract_banios(text):
    count = extract_count(
        text,
        [
            r"([0-9]+)\s+BA\S*OS?\s+COMPLETOS?",
            r"([0-9]+)\s+BA\S*OS?",
            r"BA\S*OS?\s*[:\-]?\s*([0-9]+)",
            r"([0-9]+)\s+BATH",
        ],
    )
    if count:
        return count

    source = normalize_text(text)
    if not re.search(r"\bBA\S*OS?\b", source):
        return None

    # Solo cuenta un calificativo (social, principal, etc.) si aparece pegado a
    # la palabra "bano/banos" en el texto; una palabra suelta en otra parte del
    # anuncio (ej. "avenida principal") no debe sumar un bano.
    qualifier_group = "|".join(BATHROOM_QUALIFIER_WORDS)
    pairs = re.findall(
        rf"BA\S*OS?\s+({qualifier_group})\b|\b({qualifier_group})\s+(?:CON\s+)?BA\S*OS?\b",
        source,
    )
    qualifiers = {word for pair in pairs for word in pair if word}
    if qualifiers:
        return len(qualifiers)

    return 1


ORDINAL_FLOOR_WORDS = {
    "PRIMER": 1, "PRIMERO": 1, "PRIMERA": 1,
    "SEGUNDO": 2, "SEGUNDA": 2,
    "TERCER": 3, "TERCERO": 3, "TERCERA": 3,
    "CUARTO": 4, "CUARTA": 4,
    "QUINTO": 5, "QUINTA": 5,
    "SEXTO": 6, "SEXTA": 6,
}


def extract_pisos(text):
    count = extract_count(
        text,
        [
            r"([0-9]+)\s+PISOS?",
            r"PISO\s+([0-9]+)",
            r"([0-9]+)\s*(?:ER|DO|RO|TO|VO)?\s*PISO",
            r"NIVEL\s+([0-9]+)",
            r"([0-9]+)\s+NIVELES?",
        ],
    )
    if count:
        return count

    source = normalize_text(text)
    match = re.search(
        r"\b(PRIMER|PRIMERO|PRIMERA|SEGUNDO|SEGUNDA|TERCER|TERCERO|TERCERA|"
        r"CUARTO|CUARTA|QUINTO|QUINTA|SEXTO|SEXTA)\s+(?:PISO|NIVEL)\b",
        source,
    )
    if match:
        return ORDINAL_FLOOR_WORDS.get(match.group(1))
    return None


PARKING_WORD_TO_NUMBER = {
    "UN": 1, "UNO": 1, "DOS": 2, "TRES": 3, "CUATRO": 4,
    "DOBLE": 2, "TRIPLE": 3,
}


def extract_parqueaderos(text):
    source = normalize_text(text)
    # Un "parqueadero comunal" es un cupo compartido del conjunto, no un cupo
    # privado del inmueble: no debe contarse como parqueadero propio.
    count = extract_count(
        source,
        [
            r"([0-9]+)\s+PARQUEADEROS?(?!\s+COMUNAL)",
            r"([0-9]+)\s+GARAJES?",
            r"([0-9]+)\s+COCHERAS?",
            r"([0-9]+)\s+PARKING",
            r"PARQUEADEROS?\s*[:\-]?\s*([0-9]+)",
            r"GARAJES?\s*[:\-]?\s*([0-9]+)",
        ],
    )
    if count:
        return count

    match = re.search(
        r"\b(UN|UNO|DOS|TRES|CUATRO|DOBLE|TRIPLE)\s+(?:PARQUEADEROS?(?!\s+COMUNAL)|GARAJES?|COCHERAS?|PARKING)\b",
        source,
    )
    if match:
        return PARKING_WORD_TO_NUMBER.get(match.group(1))

    match = re.search(
        r"\b(?:PARQUEADEROS?(?!\s+COMUNAL)|GARAJES?|COCHERAS?|PARKING)\s+(DOBLE|TRIPLE)\b",
        source,
    )
    if match:
        return PARKING_WORD_TO_NUMBER.get(match.group(1))

    non_communal_source = re.sub(r"\bPARQUEADEROS?\s+COMUNAL(?:ES)?\b", "", source)
    if re.search(r"\b(GARAJE|PARQUEADERO|PARQUEADEROS|COCHERA|PARKING)\b", non_communal_source):
        return 1
    return None


def extract_administracion(text):
    source = normalize_text(text)
    match = re.search(
        r"\bADM(?:INISTRACI\S*)?\.?\s*[:\-]?\s*\$?\s*"
        r"([0-9]{1,3}(?:[\.,][0-9]{3})*|[0-9]+)\s*(MIL)?",
        source,
    )
    if not match:
        return None
    value = parse_money_digits(match.group(1))
    if not value:
        return None
    if match.group(2):
        value *= 1000
    if 0 < value < 10_000_000:
        return value
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


def extract_image_urls(page, listing_url=None):
    current_item_id = extract_marketplace_id(listing_url)

    # La tira de miniaturas del visor puede cargar las fotos con lazy loading
    # al hacer scroll horizontal. Se fuerza ese scroll antes de leer el DOM
    # para que todas las miniaturas terminen con su <img src> resuelto.
    try:
        page.evaluate(
            """
            () => {
                const thumbs = Array.from(
                    document.querySelectorAll('[aria-label^="Miniatura"],[aria-label^="Thumbnail"]')
                )
                if (!thumbs.length) return
                let container = thumbs[0].parentElement
                for (let i = 0; i < 6 && container; i++) {
                    if (container.scrollWidth > container.clientWidth) break
                    container = container.parentElement
                }
                if (container && container.scrollWidth > container.clientWidth) {
                    container.scrollLeft = container.scrollWidth
                }
            }
            """
        )
        page.wait_for_timeout(400)
    except Exception:
        pass

    try:
        images = page.evaluate(
            """
            (currentItemId) => {
                const itemIdFromHref = (href) => {
                    const match = String(href || '').match(/\\/marketplace\\/item\\/(\\d+)/)
                    return match ? match[1] : null
                }

                // Estrategia principal: cada foto propia del anuncio esta marcada
                // con aria-label="Miniatura N" (o "Thumbnail N" en ingles) dentro
                // de la tira de miniaturas del visor. Publicidad, patrocinados,
                // sugeridos, perfil del vendedor y publicaciones relacionadas
                // nunca aparecen dentro de esa tira, asi que no requieren filtros
                // heuristicos adicionales.
                const thumbs = Array.from(
                    document.querySelectorAll('[aria-label^="Miniatura"],[aria-label^="Thumbnail"]')
                )
                if (thumbs.length) {
                    const seenSrc = new Set()
                    const ordered = thumbs
                        .map((thumb) => {
                            const label = thumb.getAttribute('aria-label') || ''
                            const indexMatch = label.match(/(\\d+)\\s*$/)
                            const img = thumb.querySelector('img')
                            return {
                                index: indexMatch ? parseInt(indexMatch[1], 10) : 0,
                                src: img ? (img.currentSrc || img.src || '') : '',
                                width: img ? (img.naturalWidth || img.width || 0) : 0,
                                height: img ? (img.naturalHeight || img.height || 0) : 0,
                            }
                        })
                        .filter((item) => item.src && !seenSrc.has(item.src) && seenSrc.add(item.src))
                        .sort((a, b) => a.index - b.index)
                    if (ordered.length) {
                        return ordered.map((item) => ({
                            src: item.src,
                            width: item.width,
                            height: item.height,
                            alt: '',
                            top: 0,
                            area: 0,
                            linkedItemId: currentItemId,
                            isOtherListing: false,
                            isProfileImage: false,
                            isSponsored: false,
                            isBelowExcluded: false,
                            trusted: true,
                        }))
                    }
                }

                // Respaldo: si el visor no expone miniaturas identificables (ej.
                // una publicacion con una sola foto), se reutiliza el escaneo
                // heuristico anterior por posicion y marcadores de texto.
                const excludedMarkers = [
                    'PUBLICACIONES RELACIONADAS',
                    'RELATED LISTINGS',
                    'MAS PUBLICACIONES DEL VENDEDOR',
                    'MÁS PUBLICACIONES DEL VENDEDOR',
                    'MORE FROM THIS SELLER',
                    'MAS COMO ESTE',
                    'MÁS COMO ESTE',
                    'MORE LIKE THIS',
                    'PATROCINADO',
                    'SPONSORED',
                    'PUBLICIDAD',
                    'ANUNCIO',
                    'PRODUCTOS SUGERIDOS',
                    'ARTICULOS SUGERIDOS',
                    'ARTÍCULOS SUGERIDOS',
                    'SUGGESTED FOR YOU',
                    'RECOMENDADO PARA TI',
                    'RECOMENDADOS PARA TI',
                    'RECOMENDADOS'
                ]
                let excludedTop = Number.POSITIVE_INFINITY
                for (const element of document.querySelectorAll('span,h2,h3,div[role="heading"]')) {
                    const text = (element.innerText || element.textContent || '').trim().toUpperCase()
                    if (!text || !excludedMarkers.some((marker) => text.includes(marker))) continue
                    const rect = element.getBoundingClientRect()
                    if (rect.width > 0 && rect.height > 0) {
                        excludedTop = Math.min(excludedTop, rect.top + window.scrollY)
                    }
                }

                return Array.from(document.images).map((img) => {
                    const rect = img.getBoundingClientRect()
                    const itemAnchor = img.closest('a[href*="/marketplace/item/"]')
                    const profileAnchor = img.closest('a[href*="/marketplace/profile/"],a[href*="/profile.php"],a[href*="/people/"]')
                    const sponsoredAncestor = img.closest(
                        '[aria-label*="Sponsored" i],[aria-label*="Patrocinado" i],[aria-label*="Suggested" i],[aria-label*="Sugerido" i]'
                    )
                    const linkedItemId = itemAnchor ? itemIdFromHref(itemAnchor.href || itemAnchor.getAttribute('href')) : null
                    const top = rect.top + window.scrollY
                    return {
                        src: img.currentSrc || img.src || '',
                        width: img.naturalWidth || Math.round(rect.width) || img.width || 0,
                        height: img.naturalHeight || Math.round(rect.height) || img.height || 0,
                        alt: img.alt || '',
                        top,
                        area: Math.round((rect.width || 0) * (rect.height || 0)),
                        linkedItemId,
                        isOtherListing: Boolean(currentItemId && linkedItemId && linkedItemId !== currentItemId),
                        isProfileImage: Boolean(profileAnchor),
                        isSponsored: Boolean(sponsoredAncestor),
                        isBelowExcluded: Number.isFinite(excludedTop) && top > excludedTop
                    }
                })
            }
            """,
            current_item_id,
        )
    except Exception:
        images = []

    image_urls = []
    seen = set()
    for image in images:
        src = image.get("src") or ""
        width = int(image.get("width") or 0)
        height = int(image.get("height") or 0)
        # Las imagenes que vienen de la tira de miniaturas ya estan garantizadas
        # a pertenecer al anuncio actual (ver estrategia principal arriba), asi
        # que no pasan por los filtros heuristicos de posicion/tamano pensados
        # para el escaneo de respaldo (donde naturalWidth puede venir en 0 si la
        # miniatura aun no termino de decodificar).
        trusted = bool(image.get("trusted"))
        if not src or src in seen:
            continue
        if not trusted and (
            image.get("isOtherListing")
            or image.get("isProfileImage")
            or image.get("isSponsored")
            or image.get("isBelowExcluded")
        ):
            continue
        if "static.xx.fbcdn.net" in src or "emoji.php" in src or "rsrc.php" in src:
            continue
        if "fbcdn.net" not in src and "scontent" not in src:
            continue
        if not trusted and (width < 160 or height < 160):
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

    # Prioridad de precio: 1) JSON estructurado de Marketplace (mas confiable),
    # 2) precio visible/formateado del propio JSON, 3) texto libre (descripcion/
    # titulo) como ultimo recurso. Antes se usaba primero el texto libre, lo que
    # permitia que un numero de telefono ganara sobre el precio real.
    price = (
        _sane_price(embedded.get("price_amount"))
        or _sane_price(parse_money_digits(embedded.get("price_text")))
        or extract_price(full_text)
    )
    if not price:
        print(f"[SKIP] Venta sin precio real: {title}")
        return None, html, [], "sin_precio"

    tipo_inmueble = extract_property_type(title, full_text)

    item_id = extract_marketplace_id(link)
    barrio = extract_barrio(title, full_text)
    ciudad = extract_city(title, full_text)
    location = embedded.get("location") or extract_location(listing_text) or extract_location(body_text)

    # La validacion de ciudad usa la ubicacion real declarada por Marketplace
    # (location) como fuente principal, no solo si aparece la palabra "Pasto"
    # en el texto libre (el vendedor puede mencionar "Pasto" como referencia de
    # cercania aunque el inmueble este en otro municipio).
    if is_explicitly_out_of_city(title, full_text, location_text=location):
        print(f"[SKIP] Publicacion parece estar fuera de Pasto: {title}")
        return None, html, [], "fuera_de_pasto"

    location_result = resolve_pasto_location(
        barrio, title=title, description=full_text, address=location, city=ciudad
    )
    print(f"[UBICACION] {location_diagnostic(location_result)}")
    if location_result.outside_municipality:
        return None, html, [], "fuera_de_pasto"
    barrio = location_result.value if location_result.accepted else None
    image_urls = extract_image_urls(page, link)
    seller = extract_seller(page, body_text)
    area_details = extract_area_details(full_text)

    notes = {
        "titulo_facebook": title,
        "ubicacion_facebook": location,
        "vendedor_facebook": seller,
        "imagenes_detectadas": image_urls,
        "min_sale_price": MIN_SALE_PRICE,
        "contenido_filtrado": listing_text[:3000],
        "normalizacion_ubicacion": location_diagnostic(location_result),
        "area": area_details,
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
        "ph": None,
        "estrato": extract_count(full_text, [r"ESTRATO\s+([0-9])"]),
        "descripcion": description,
        "precio": price,
        "m2": area_details["lot_area_m2"] if area_details["lot_area_m2"] is not None else area_details["built_area_m2"],
        "m2_construido": area_details["built_area_m2"],
        "antiguedad": None,
        "pisos": extract_pisos(full_text),
        "habitaciones": extract_count(
            full_text,
            [
                r"([0-9]+)\s+HABITACI\S*",
                r"([0-9]+)\s+ALCOBAS?",
                # \b(?!\s+DE\s+BA) evita contar "2 cuartos de bano" como habitaciones
                # (el \b es necesario para que la S opcional no deje "escapar" al lookahead).
                r"([0-9]+)\s+CUARTOS?\b(?!\s+DE\s+BA)",
                r"([0-9]+)\s+DORMITORIOS?",
                r"HABITACI\S*\s*[:\-]?\s*([0-9]+)",
                r"ALCOBAS?\s*[:\-]?\s*([0-9]+)",
                r"DORMITORIOS?\s*[:\-]?\s*([0-9]+)",
            ],
        ),
        "banios": extract_banios(full_text),
        "parqueadero": extract_parqueaderos(full_text),
        "administracion": extract_administracion(full_text),
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
    print("[ERROR] No se pudo conectar a MySQL.")
    print(f"[ERROR] Detalle: {error}")
    print(
        "[ERROR] Config usada: "
        f"DB_HOST={os.getenv('DB_HOST', 'localhost')} "
        f"DB_PORT={os.getenv('DB_PORT', DB_DEFAULT_PORT)} "
        f"DB_USER={os.getenv('DB_USER', 'root')} "
        f"DB_NAME={os.getenv('DB_NAME', 'db_inmobiliary_data')} "
        "DB_PASSWORD=definida_en_entorno_o_env"
    )
    print("[ERROR] Soluciones:")
    print("[ERROR] - Revisa que DB_PASSWORD sea la clave correcta de tu MySQL.")
    print(f"[ERROR] - Revisa el puerto: $env:DB_PORT=\"{DB_DEFAULT_PORT}\" o el que use tu MySQL.")
    print("[ERROR] - Para probar sin guardar: $env:FACEBOOK_DRY_RUN=\"true\"")


def get_connection():
    if mysql is None:
        raise RuntimeError("mysql-connector-python no esta instalado.")
    return mysql.connector.connect(**get_db_config(DB_DEFAULT_PORT))


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
            SOURCE_NAME,
            "https://www.facebook.com/marketplace/",
            "marketplace",
            "Scraper de inmuebles en venta en Pasto desde Facebook Marketplace",
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
            parqueadero, administracion
        )
        VALUES (
            %(fuente_id)s, %(codigo_externo)s, %(link_origen)s, %(links_adicionales)s,
            %(coordenadas)s, %(latitud)s, %(longitud)s, %(direccion)s, %(ciudad)s, %(barrio)s,
            %(tipo_inmueble)s, %(ph)s, %(estrato)s, %(descripcion)s, %(precio)s, %(m2)s,
            %(m2_construido)s, %(antiguedad)s, %(pisos)s, %(habitaciones)s, %(banios)s,
            %(parqueadero)s, %(administracion)s
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
    path = html_dir / f"facebook_{sanitize_filename(codigo_archivo)}.html"
    with open(path, "w", encoding="utf-8") as file:
        file.write(html)
    return path


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
            def fetch_image():
                request = Request(image_url, headers={"User-Agent": USER_AGENT})
                with urlopen(request, timeout=15) as response:
                    return response.read()

            content = with_retry(fetch_image, f"Descargar imagen {image_url}")
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
    print(f"[INFO] FACEBOOK_SEARCH_CITY: {SEARCH_CITY}")
    print(f"[INFO] FACEBOOK_HEADLESS: {HEADLESS}")
    print(f"[INFO] FACEBOOK_DRY_RUN: {DRY_RUN}")
    print(f"[INFO] FACEBOOK_MAX_SCROLLS: {MAX_SCROLLS}")
    print(f"[INFO] FACEBOOK_MIN_SALE_PRICE: {MIN_SALE_PRICE}")
    print(f"[INFO] FACEBOOK_SPLIT_PRICE_BUCKETS: {SPLIT_PRICE_BUCKETS}")
    print(f"[INFO] Listados Facebook planeados: {len(build_search_urls())}")
    print(f"[INFO] Perfil Chromium: {PROFILE_DIR.resolve()}")

    connection = None
    fuente_id = None
    total_nuevas = 0
    total_saltadas = 0
    total_omitidas = 0
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
                    detect_duplicates_safely(connection, publicacion_id)
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
    print(f"[RESUMEN] Nuevas guardadas/aceptadas: {total_nuevas}")
    print(f"[RESUMEN] Saltadas porque ya existian: {total_saltadas}")
    print(f"[RESUMEN] Omitidas por filtro/precio/tipo: {total_omitidas}")
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
