import os
import re
import json
import time
import math
import hashlib
import requests
import mysql.connector

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin
from dotenv import load_dotenv
from mysql.connector import IntegrityError
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from scraper_audit import ScraperAudit


# ==========================================================
# CONFIGURACIÓN GENERAL
# ==========================================================

load_dotenv()

SEARCH_URL = "https://www.ciencuadras.com/venta/pasto"
BASE_URL = "https://www.ciencuadras.com"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "boludo123"),
    "database": os.getenv("DB_NAME", "db_inmobiliary_data"),
}

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
# 0 = recorrer todas las paginas detectadas.
MAX_PAGES = int(os.getenv("MAX_PAGES", "0"))

GALLERY_VISIBLE_WAIT_MS = int(os.getenv("GALLERY_VISIBLE_WAIT_MS", "400"))
GALLERY_OPEN_WAIT_MS = int(os.getenv("GALLERY_OPEN_WAIT_MS", "600"))
GALLERY_CLICK_WAIT_MS = int(os.getenv("GALLERY_CLICK_WAIT_MS", "250"))
GALLERY_STALLED_CLICKS = int(os.getenv("GALLERY_STALLED_CLICKS", "2"))
GALLERY_MAX_NEXT_CLICKS = int(os.getenv("GALLERY_MAX_NEXT_CLICKS", "40"))

IMAGE_DOWNLOAD_WORKERS = int(os.getenv("IMAGE_DOWNLOAD_WORKERS", "6"))
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "12"))

SEARCH_LOAD_WAIT_MS = int(os.getenv("SEARCH_LOAD_WAIT_MS", "2500"))
DETAIL_LOAD_WAIT_MS = int(os.getenv("DETAIL_LOAD_WAIT_MS", "1200"))
PAGINATION_LOAD_WAIT_MS = int(os.getenv("PAGINATION_LOAD_WAIT_MS", "2000"))
SCROLL_WAIT_MS = int(os.getenv("SCROLL_WAIT_MS", "1000"))
REQUEST_PAUSE_SECONDS = float(os.getenv("REQUEST_PAUSE_SECONDS", "0.4"))

EVIDENCE_DIR = Path("evidencias")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================================
# UTILIDADES
# ==========================================================

def clean_text(value):
    if not value:
        return None

    value = re.sub(r"\s+", " ", str(value))
    value = value.strip()

    return value if value else None


def only_digits(value):
    if not value:
        return None

    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def parse_decimal(value):
    if not value:
        return None

    value = str(value).replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", value)

    if not match:
        return None

    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_int(value):
    if value is None:
        return None

    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def sanitize_filename(value):
    value = value or str(int(time.time()))
    value = re.sub(r"[^a-zA-Z0-9_-]", "_", str(value))
    return value[:120]


def file_hash(path):
    sha256 = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def get_lines(text):
    if not text:
        return []

    return [line.strip() for line in text.splitlines() if line.strip()]


def value_after_label(lines, label):
    label_lower = label.lower().replace(":", "").strip()

    for index, line in enumerate(lines):
        line_clean = line.lower().replace(":", "").strip()

        if line_clean.startswith(label_lower):
            if ":" in line:
                possible_value = line.split(":", 1)[1].strip()

                if possible_value:
                    return possible_value

            for next_index in range(index + 1, min(index + 5, len(lines))):
                next_line = clean_text(lines[next_index])

                if next_line:
                    return next_line

    return None


def extract_section(lines, start_label, stop_labels):
    start_index = None

    for index, line in enumerate(lines):
        if line.strip().lower() == start_label.lower():
            start_index = index + 1
            break

    if start_index is None:
        return None

    content = []

    for line in lines[start_index:]:
        lower = line.lower()

        if any(lower.startswith(stop.lower()) for stop in stop_labels):
            break

        content.append(line)

    return clean_text(" ".join(content))


# ==========================================================
# EXTRACCIÓN DE DATOS
# ==========================================================

TIPOS_INMUEBLE = [
    "Apartamento",
    "Casa",
    "Lote",
    "Oficina",
    "Local",
    "Apartaestudio",
    "Edificio",
    "Consultorio",
    "Finca"
]


def extract_title_parts(title):
    """
    Extrae datos del h1 cuando viene con formato:
    "Casa en venta, El dorado"
    """

    title = clean_text(title)

    if not title or "," not in title:
        return None, None

    tipo_text, barrio_text = title.split(",", 1)

    tipo_inmueble = None

    for tipo in TIPOS_INMUEBLE:
        if re.search(rf"\b{re.escape(tipo)}\b", tipo_text, re.IGNORECASE):
            tipo_inmueble = tipo
            break

    barrio = clean_text(barrio_text)

    return tipo_inmueble, barrio


def extract_total_results(text):
    if not text:
        return None

    match = re.search(r"de\s+([\d\.,]+)\s+resultados", text, re.IGNORECASE)

    if match:
        return only_digits(match.group(1))

    match = re.search(r"([\d\.,]+)\s+resultados", text, re.IGNORECASE)

    if match:
        return only_digits(match.group(1))

    return None


def extract_result_window(text):
    if not text:
        return None

    match = re.search(
        r"([\d\.,]+)\s*[-\u2013]\s*([\d\.,]+)\s+de\s+([\d\.,]+)\s+resultados",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    start = only_digits(match.group(1))
    end = only_digits(match.group(2))
    total = only_digits(match.group(3))

    if start and end and total and end >= start:
        return start, end, total

    return None


def extract_codigo(text):
    if not text:
        return None

    patterns = [
        r"Código:\s*([A-Za-z0-9\-]+)",
        r"Código\s+([A-Za-z0-9\-]+)",
        r"Cod:\s*([A-Za-z0-9\-]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return clean_text(match.group(1))

    return None


def extract_precio(text):
    if not text:
        return None

    patterns = [
        r"Valor de compra:\s*\$?\s*([\d\.,]+)",
        r"Precio:\s*\$?\s*([\d\.,]+)",
        r"\$\s*([\d\.,]{5,})"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return only_digits(match.group(1))

    return None


def extract_number_by_keywords(text, keywords):
    if not text:
        return None

    for keyword in keywords:
        patterns = [
            rf"{keyword}\s*[:\-]?\s*(\d+)",
            rf"(\d+)\s+{keyword}"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                return int(match.group(1))

    return None


def extract_location(lines, title=None, text=None):
    _, title_barrio = extract_title_parts(title)

    if title_barrio:
        return "Pasto", title_barrio, f"{title_barrio}, Pasto, Nariño"

    full_text = " ".join([
        title or "",
        text or "",
        " ".join(lines or [])
    ])

    for line in lines:
        if "Pasto" in line:
            parts = [part.strip() for part in line.split(",") if part.strip()]

            ciudad = "Pasto"
            barrio = None

            for part in parts:
                part_lower = part.lower()

                if "pasto" not in part_lower and "nariño" not in part_lower:
                    barrio = part
                    break

            direccion = clean_text(", ".join(
                [value for value in [barrio, ciudad, "Nariño"] if value]
            ))

            return ciudad, barrio, direccion

    pattern = re.search(
        r"ubicado en Nariño en Pasto en\s+([^,]+)",
        full_text,
        re.IGNORECASE
    )

    if pattern:
        barrio = clean_text(pattern.group(1))
        ciudad = "Pasto"
        direccion = clean_text(f"{barrio}, Pasto, Nariño")

        return ciudad, barrio, direccion

    pattern = re.search(
        r"Pasto en\s+([^,]+)",
        full_text,
        re.IGNORECASE
    )

    if pattern:
        barrio = clean_text(pattern.group(1))
        ciudad = "Pasto"
        direccion = clean_text(f"{barrio}, Pasto, Nariño")

        return ciudad, barrio, direccion

    return "Pasto", None, "Pasto, Nariño"


def extract_coordinates_from_source(html, text):
    """
    Solo extrae coordenadas si la publicación o el HTML las proporciona.
    No usa Google Maps ni ninguna API externa.
    """

    source = f"{html or ''}\n{text or ''}"

    patterns = [
        r'"latitude"\s*:\s*(-?\d+(?:\.\d+)?).*?"longitude"\s*:\s*(-?\d+(?:\.\d+)?)',
        r'"lat"\s*:\s*(-?\d+(?:\.\d+)?).*?"lng"\s*:\s*(-?\d+(?:\.\d+)?)',
        r'data-lat\s*=\s*["\'](-?\d+(?:\.\d+)?)["\'].*?data-lng\s*=\s*["\'](-?\d+(?:\.\d+)?)["\']',
        r'data-latitude\s*=\s*["\'](-?\d+(?:\.\d+)?)["\'].*?data-longitude\s*=\s*["\'](-?\d+(?:\.\d+)?)["\']',
        r'coordenadas?\s*[:=]\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)

        if match:
            latitud = float(match.group(1))
            longitud = float(match.group(2))

            if -5 <= latitud <= 15 and -82 <= longitud <= -66:
                coordenadas = f"{latitud},{longitud}"
                return coordenadas, latitud, longitud

    geojson_match = re.search(
        r'"coordinates"\s*:\s*\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]',
        source,
        re.IGNORECASE
    )

    if geojson_match:
        longitud = float(geojson_match.group(1))
        latitud = float(geojson_match.group(2))

        if -5 <= latitud <= 15 and -82 <= longitud <= -66:
            coordenadas = f"{latitud},{longitud}"
            return coordenadas, latitud, longitud

    return None, None, None


def extract_tipo_inmueble(title, text):
    title_tipo, _ = extract_title_parts(title)

    if title_tipo:
        return title_tipo

    source = f"{title or ''} {text or ''}".lower()

    for tipo in TIPOS_INMUEBLE:
        if tipo.lower() in source:
            return tipo

    return None


def extract_ph(description):
    if not description:
        return None

    patterns = [
        r"(Conjunto\s+[A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s\-_]+)",
        r"(Edificio\s+[A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s\-_]+)",
        r"(Condominio\s+[A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s\-_]+)",
        r"(Urbanización\s+[A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s\-_]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)

        if match:
            return clean_text(match.group(1))

    return None


def extract_pisos(description):
    if not description:
        return None

    match = re.search(
        r"(\d+)\s*(pisos|piso|niveles|nivel)",
        description,
        re.IGNORECASE
    )

    return int(match.group(1)) if match else None


def extract_administracion(text):
    if not text:
        return None

    match = re.search(
        r"administraci[oó]n[:\s\$]*([\d\.,]+)",
        text,
        re.IGNORECASE
    )

    if match:
        return only_digits(match.group(1))

    return None


# ==========================================================
# BASE DE DATOS
# ==========================================================

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def get_or_create_fuente_id(connection):
    sql = """
        INSERT INTO fuentes_inmobiliarias
        (nombre, url_base, tipo_fuente, activa, descripcion)
        VALUES (%s, %s, %s, TRUE, %s)
        ON DUPLICATE KEY UPDATE
            id = LAST_INSERT_ID(id),
            activa = TRUE
    """

    values = (
        "Ciencuadras",
        "https://www.ciencuadras.com",
        "portal",
        "Portal inmobiliario usado para extracción automática de publicaciones en Pasto."
    )

    cursor = connection.cursor()
    cursor.execute(sql, values)
    connection.commit()

    fuente_id = cursor.lastrowid
    cursor.close()

    return fuente_id


def publicacion_ya_existe(connection, link_origen):
    """
    Verifica si la publicación ya existe en la base de datos.
    Si existe, se salta completamente.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM publicaciones
        WHERE link_origen = %s
        LIMIT 1
        """,
        (link_origen,)
    )

    result = cursor.fetchone()
    cursor.close()

    return result[0] if result else None


def insert_publicacion(connection, data):
    """
    Inserta solo publicaciones nuevas.
    No actualiza publicaciones existentes.
    No inserta precio_m2 ni precio_m2_construido porque MySQL los calcula solo.
    """

    sql = """
        INSERT INTO publicaciones (
            fuente_id,
            codigo_externo,
            link_origen,
            links_adicionales,
            coordenadas,
            latitud,
            longitud,
            direccion,
            ciudad,
            barrio,
            tipo_inmueble,
            ph,
            estrato,
            descripcion,
            precio,
            m2,
            m2_construido,
            antiguedad,
            pisos,
            habitaciones,
            banios,
            parqueadero,
            administracion,
            notas
        )
        VALUES (
            %(fuente_id)s,
            %(codigo_externo)s,
            %(link_origen)s,
            %(links_adicionales)s,
            %(coordenadas)s,
            %(latitud)s,
            %(longitud)s,
            %(direccion)s,
            %(ciudad)s,
            %(barrio)s,
            %(tipo_inmueble)s,
            %(ph)s,
            %(estrato)s,
            %(descripcion)s,
            %(precio)s,
            %(m2)s,
            %(m2_construido)s,
            %(antiguedad)s,
            %(pisos)s,
            %(habitaciones)s,
            %(banios)s,
            %(parqueadero)s,
            %(administracion)s,
            %(notas)s
        )
    """

    cursor = connection.cursor()
    cursor.execute(sql, data)
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
        (publicacion_id, tipo, ruta_archivo)
    )

    exists = cursor.fetchone()

    if exists:
        cursor.close()
        return

    hash_archivo = None

    if ruta_archivo and Path(ruta_archivo).exists():
        hash_archivo = file_hash(ruta_archivo)

    cursor.execute(
        """
        INSERT INTO evidencias_publicacion (
            publicacion_id,
            tipo,
            ruta_archivo,
            url_original,
            hash_archivo
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            publicacion_id,
            tipo,
            ruta_archivo,
            url_original,
            hash_archivo
        )
    )

    connection.commit()
    cursor.close()


# ==========================================================
# EVIDENCIAS POR ID DE PUBLICACIÓN
# ==========================================================

def get_publication_evidence_dirs(publicacion_id):
    """
    Crea carpetas separadas por ID de publicación.

    Ejemplo:
    evidencias/publicacion_1/html
    evidencias/publicacion_1/imagenes
    evidencias/publicacion_1/screenshots
    """

    base_dir = EVIDENCE_DIR / f"publicacion_{publicacion_id}"

    html_dir = base_dir / "html"
    img_dir = base_dir / "imagenes"
    screenshot_dir = base_dir / "screenshots"

    for folder in [html_dir, img_dir, screenshot_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    return html_dir, img_dir, screenshot_dir


def save_html(html, codigo_archivo, publicacion_id):
    html_dir, _, _ = get_publication_evidence_dirs(publicacion_id)

    filename = f"ciencuadras_{sanitize_filename(codigo_archivo)}.html"
    path = html_dir / filename

    with open(path, "w", encoding="utf-8") as file:
        file.write(html)

    return path


def save_screenshot(page, codigo_archivo, publicacion_id):
    _, _, screenshot_dir = get_publication_evidence_dirs(publicacion_id)

    filename = f"ciencuadras_{sanitize_filename(codigo_archivo)}.png"
    path = screenshot_dir / filename

    try:
        page.screenshot(path=str(path), full_page=True)
        return path
    except Exception as error:
        print(f"[WARN] No se pudo guardar screenshot: {error}")
        return None


GALLERY_SELECTORS = (
    ".carousel-gallery, "
    "article.gallery-contain-wrapper, "
    "ciencuadras-mini-gallery, "
    "ciencuadras-cc-p-gallery-full, "
    ".full-gallery"
)

FULL_GALLERY_SELECTORS = (
    ".p-dialog, "
    ".p-galleria, "
    ".full-gallery, "
    "ciencuadras-cc-p-gallery, "
    "ciencuadras-cc-p-gallery-full"
)

IMAGE_URL_COLLECTOR_JS = """
containers => {
    const urls = [];

    const addCandidate = (candidates, value) => {
        if (!value) {
            return;
        }

        String(value)
            .split(',')
            .map(item => item.trim().split(/\\s+/)[0])
            .filter(Boolean)
            .forEach(url => candidates.push(url));
    };

    const isBlockedImage = (url) => {
        const lower = String(url).toLowerCase();

        return lower.includes('default-image')
            || lower.includes('/sources/images/default')
            || lower.includes('zgvmyxvsdc1pbwfnzs5wbm')
            || lower.includes('logo')
            || lower.includes('.svg')
            || lower.startsWith('data:');
    };

    const selectBestUrl = (candidates) => {
        const cleanCandidates = candidates.filter(url => !isBlockedImage(url));
        const original = cleanCandidates.find(url => url.includes('www-img-cc.s3.amazonaws.com'));

        if (original) {
            return original;
        }

        return cleanCandidates[0] || null;
    };

    const collectFromElement = (element) => {
        const candidates = [];

        addCandidate(candidates, element.getAttribute('data-src'));
        addCandidate(candidates, element.getAttribute('lazyload'));
        addCandidate(candidates, element.getAttribute('srcset'));
        addCandidate(candidates, element.getAttribute('src'));
        addCandidate(candidates, element.currentSrc);

        const bestUrl = selectBestUrl(candidates);

        if (bestUrl) {
            urls.push(bestUrl);
        }
    };

    containers.forEach(container => {
        container.querySelectorAll('picture').forEach(picture => {
            const candidates = [];

            picture.querySelectorAll('source').forEach(source => {
                addCandidate(candidates, source.getAttribute('srcset'));
                addCandidate(candidates, source.getAttribute('data-src'));
                addCandidate(candidates, source.getAttribute('lazyload'));
            });

            picture.querySelectorAll('img').forEach(img => {
                addCandidate(candidates, img.getAttribute('data-src'));
                addCandidate(candidates, img.currentSrc);
                addCandidate(candidates, img.getAttribute('src'));
                addCandidate(candidates, img.getAttribute('srcset'));
            });

            const bestUrl = selectBestUrl(candidates);

            if (bestUrl) {
                urls.push(bestUrl);
            }
        });

        container.querySelectorAll('source, img').forEach(element => {
            if (element.closest('picture')) {
                return;
            }

            collectFromElement(element);
        });

        container.querySelectorAll('[style*="background-image"]').forEach(element => {
            const style = element.getAttribute('style') || '';
            const matches = Array.from(style.matchAll(/url\\(["']?([^"')]+)["']?\\)/gi));

            matches.forEach(match => {
                if (match[1] && !isBlockedImage(match[1])) {
                    urls.push(match[1]);
                }
            });
        });
    });

    return Array.from(new Set(urls));
}
"""


def normalize_image_urls(image_urls):
    cleaned = []

    for image_url in image_urls or []:
        if not str(image_url).strip():
            continue

        image_url = urljoin(BASE_URL, str(image_url).strip())
        lower = image_url.lower()

        if lower.startswith("data:"):
            continue

        if ".svg" in lower:
            continue

        if "default-image" in lower or "zgvmyxvsdc1pbwfnzs5wbm" in lower:
            continue

        if "logo" in lower:
            continue

        if image_url not in cleaned:
            cleaned.append(image_url)

    return cleaned


def collect_image_urls_from_selectors(page, selectors):
    try:
        image_urls = page.eval_on_selector_all(
            selectors,
            IMAGE_URL_COLLECTOR_JS
        )

        return normalize_image_urls(image_urls)
    except Exception:
        return []


def click_open_full_gallery(page):
    try:
        return page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);

                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                };

                const containers = Array.from(
                    document.querySelectorAll('.carousel-gallery, article.gallery-contain-wrapper')
                );

                for (const container of containers) {
                    const buttons = Array.from(
                        container.querySelectorAll('button, a, [role="button"], ciencuadras-button')
                    );

                    const target = buttons.find(el => {
                        const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        const qa = (
                            el.getAttribute('data-qa-id')
                            || el.getAttribute('tagqa')
                            || ''
                        ).toLowerCase();

                        return isVisible(el)
                            && (
                                text.includes('ver fotos')
                                || qa.includes('open_full_gallery')
                                || qa.includes('mini_gallery')
                            );
                    });

                    if (target) {
                        const clickable = target.closest('button, a, [role="button"]') || target;
                        clickable.scrollIntoView({ block: 'center' });
                        clickable.click();
                        return true;
                    }
                }

                return false;
            }
            """
        )
    except Exception:
        return False


def click_next_gallery_image(page):
    try:
        return page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);

                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                };

                const roots = Array.from(
                    document.querySelectorAll('.p-dialog, .p-galleria, .full-gallery')
                ).filter(isVisible);

                const root = roots[0] || document;
                const elements = Array.from(
                    root.querySelectorAll('button, a, span, div, [role="button"]')
                );

                const candidates = elements.filter(el => {
                    const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const title = (el.getAttribute('title') || '').toLowerCase();
                    const cls = (el.getAttribute('class') || '').toLowerCase();

                    return isVisible(el)
                        && (
                            cls.includes('next')
                            || cls.includes('chevron-right')
                            || text === '>'
                            || text === '›'
                            || aria.includes('siguiente')
                            || aria.includes('next')
                            || title.includes('siguiente')
                            || title.includes('next')
                        );
                });

                if (!candidates.length) {
                    return false;
                }

                const target = candidates[0].closest('button, a, [role="button"]') || candidates[0];
                target.click();
                return true;
            }
            """
        )
    except Exception:
        return False


def collect_full_gallery_image_urls(page):
    image_urls = []

    if not click_open_full_gallery(page):
        return image_urls

    page.wait_for_timeout(GALLERY_OPEN_WAIT_MS)

    last_count = 0
    stalled_clicks = 0

    for _ in range(GALLERY_MAX_NEXT_CLICKS):
        image_urls.extend(
            collect_image_urls_from_selectors(page, FULL_GALLERY_SELECTORS)
        )

        image_urls = normalize_image_urls(image_urls)
        current_count = len(image_urls)

        if current_count == last_count:
            stalled_clicks += 1
        else:
            stalled_clicks = 0

        last_count = current_count

        if stalled_clicks >= GALLERY_STALLED_CLICKS:
            break

        if not click_next_gallery_image(page):
            break

        page.wait_for_timeout(GALLERY_CLICK_WAIT_MS)

    return normalize_image_urls(image_urls)


def collect_image_urls(page):
    try:
        page.locator(".carousel-gallery").first.scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(GALLERY_VISIBLE_WAIT_MS)
    except Exception:
        pass

    image_urls = []
    image_urls.extend(collect_image_urls_from_selectors(page, GALLERY_SELECTORS))

    print(f"[INFO] Fotos detectadas en galeria visible: {len(normalize_image_urls(image_urls))}")

    full_gallery_urls = collect_full_gallery_image_urls(page)
    image_urls.extend(full_gallery_urls)

    image_urls = normalize_image_urls(image_urls)

    print(f"[INFO] Total fotos detectadas para descargar: {len(image_urls)}")

    return image_urls


def download_image(image_url, codigo_archivo, index, publicacion_id):
    _, img_dir, _ = get_publication_evidence_dirs(publicacion_id)

    try:
        response = requests.get(
            image_url,
                timeout=IMAGE_DOWNLOAD_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
        )

        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()

        if "png" in content_type:
            extension = ".png"
        elif "webp" in content_type:
            extension = ".webp"
        else:
            extension = ".jpg"

        filename = f"ciencuadras_{sanitize_filename(codigo_archivo)}_{index}{extension}"
        path = img_dir / filename

        with open(path, "wb") as file:
            file.write(response.content)

        return path

    except Exception as error:
        print(f"[WARN] No se pudo descargar imagen: {image_url} | {error}")
        return None


def download_images_parallel(image_urls, codigo_archivo, publicacion_id):
    if not image_urls:
        return []

    workers = max(1, min(IMAGE_DOWNLOAD_WORKERS, len(image_urls)))
    downloaded = []

    print(f"[INFO] Descargando {len(image_urls)} fotos con {workers} hilos")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                download_image,
                image_url,
                codigo_archivo,
                index,
                publicacion_id
            ): (index, image_url)
            for index, image_url in enumerate(image_urls, start=1)
        }

        for future in as_completed(futures):
            index, image_url = futures[future]

            try:
                image_path = future.result()
            except Exception as error:
                print(f"[WARN] No se pudo descargar imagen {index}: {error}")
                continue

            if image_path:
                print(f"[OK] Foto descargada {index}/{len(image_urls)}")
                downloaded.append((index, image_url, image_path))

    downloaded.sort(key=lambda item: item[0])

    return downloaded


# ==========================================================
# PAGINACIÓN Y LINKS
# ==========================================================

def get_current_page_links(page):
    try:
        links = page.eval_on_selector_all(
            "a[href*='/inmueble/']",
            """
            anchors => anchors
                .map(a => a.href)
                .filter(Boolean)
                .map(href => href.split('?')[0])
            """
        )

        return list(dict.fromkeys(links))

    except Exception:
        return []


def links_signature(page):
    links = get_current_page_links(page)
    return "|".join(sorted(links))


def wait_for_links_change(page, old_signature, timeout_seconds=12):
    start = time.time()

    while time.time() - start < timeout_seconds:
        page.wait_for_timeout(400)

        new_signature = links_signature(page)

        if new_signature and new_signature != old_signature:
            return True

    return False


def click_pagination_number(page, page_number):
    old_signature = links_signature(page)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(SCROLL_WAIT_MS)

    try:
        locator = page.get_by_text(str(page_number), exact=True)
        count = locator.count()

        for index in reversed(range(count)):
            item = locator.nth(index)

            try:
                box = item.bounding_box()

                if not box:
                    continue

                item.scroll_into_view_if_needed(timeout=3000)
                page.wait_for_timeout(250)
                item.click(timeout=3000, force=True)

                if wait_for_links_change(page, old_signature):
                    return True

            except Exception:
                continue

    except Exception:
        pass

    try:
        clicked = page.evaluate(
            """
            (pageNumber) => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);

                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                };

                const elements = Array.from(
                    document.querySelectorAll('span, li, button, a, div, [role="button"]')
                );

                const candidates = elements.filter(el => {
                    const text = (el.innerText || el.textContent || '').trim();
                    return text === String(pageNumber) && isVisible(el);
                });

                if (!candidates.length) {
                    return false;
                }

                candidates.sort((a, b) => {
                    return b.getBoundingClientRect().top - a.getBoundingClientRect().top;
                });

                for (const el of candidates) {
                    const clickable = el.closest('button, a, [role="button"], li') || el;

                    try {
                        clickable.scrollIntoView({ block: 'center' });

                        clickable.dispatchEvent(new MouseEvent('mouseover', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));

                        clickable.dispatchEvent(new MouseEvent('mousedown', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));

                        clickable.dispatchEvent(new MouseEvent('mouseup', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));

                        clickable.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));

                        return true;

                    } catch (error) {
                        continue;
                    }
                }

                return false;
            }
            """,
            page_number
        )

        if clicked and wait_for_links_change(page, old_signature):
            return True

    except Exception:
        pass

    return False


def click_next_page(page):
    old_signature = links_signature(page)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(SCROLL_WAIT_MS)

    try:
        clicked = page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);

                    return rect.width > 0
                        && rect.height > 0
                        && style.visibility !== 'hidden'
                        && style.display !== 'none';
                };

                const elements = Array.from(
                    document.querySelectorAll('button, a, span, li, div, [role="button"]')
                );

                const candidates = elements.filter(el => {
                    const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const title = (el.getAttribute('title') || '').toLowerCase();

                    const looksNext =
                        text === '>' ||
                        text.includes('siguiente') ||
                        aria.includes('siguiente') ||
                        aria.includes('next') ||
                        title.includes('siguiente') ||
                        title.includes('next');

                    return looksNext && isVisible(el);
                });

                if (!candidates.length) {
                    return false;
                }

                candidates.sort((a, b) => {
                    return b.getBoundingClientRect().top - a.getBoundingClientRect().top;
                });

                const el = candidates[0];
                const clickable = el.closest('button, a, [role="button"], li') || el;

                clickable.scrollIntoView({ block: 'center' });
                clickable.click();

                return true;
            }
            """
        )

        if clicked and wait_for_links_change(page, old_signature):
            return True

    except Exception:
        pass

    return False


def collect_publication_links(page):
    audit = ScraperAudit("Ciencuadras", SEARCH_URL)
    all_links = set()

    try:
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception as error:
        reason = f"No se pudo abrir la primera pagina de resultados: {error}"
        print(f"[ERROR] {reason}")
        audit.record_page(1, url=SEARCH_URL, status="error", reason=reason)
        return [], audit

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(SEARCH_LOAD_WAIT_MS)

    body_text = page.locator("body").inner_text(timeout=15000)
    total_results = extract_total_results(body_text)
    result_window = extract_result_window(body_text)

    if result_window:
        start, end, window_total = result_window
        total_results = total_results or window_total
        page_size = max(end - start + 1, 1)
    else:
        first_page_links_preview = get_current_page_links(page)
        page_size = len(first_page_links_preview) or None

    if total_results and page_size:
        detected_pages = math.ceil(total_results / page_size)
    else:
        detected_pages = MAX_PAGES if MAX_PAGES > 0 else 1

    if MAX_PAGES > 0:
        total_pages = min(detected_pages, MAX_PAGES)
    else:
        total_pages = detected_pages

    limit_reason = None
    if MAX_PAGES > 0 and detected_pages > total_pages:
        limit_reason = (
            f"Se revisaron {total_pages} de {detected_pages} pagina(s) porque "
            f"MAX_PAGES={MAX_PAGES} limito el recorrido."
        )

    audit.set_listing_summary(
        total_reported=total_results,
        pages_expected=detected_pages,
        pages_planned=total_pages,
        page_size=page_size,
        limit_reason=limit_reason,
    )

    print(f"[INFO] Total resultados detectados: {total_results}")
    print(f"[INFO] Resultados por pagina detectados: {page_size}")
    print(f"[INFO] Total páginas a revisar: {total_pages}")

    for current_page in range(1, total_pages + 1):
        print(f"[INFO] Revisando página {current_page} de {total_pages}")

        if current_page > 1:
            clicked = click_pagination_number(page, current_page)

            if not clicked:
                print(f"[WARN] No funcionó clic directo en página {current_page}. Intentando botón siguiente...")
                clicked = click_next_page(page)

            if not clicked:
                print(f"[WARN] No se pudo avanzar a la página {current_page}")

                debug_path = EVIDENCE_DIR / f"debug_paginacion_pagina_{current_page}.png"
                reason = "No funciono el click directo ni el boton siguiente."

                try:
                    page.screenshot(path=str(debug_path), full_page=True)
                    print(f"[INFO] Screenshot debug guardado en: {debug_path}")
                except Exception:
                    pass

                audit.record_page(
                    current_page,
                    links_count=0,
                    new_links_count=0,
                    duplicate_links_count=0,
                    status="pagination_error",
                    reason=reason,
                )
                break

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(PAGINATION_LOAD_WAIT_MS)

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(SCROLL_WAIT_MS)

        links = get_current_page_links(page)

        new_links = 0
        duplicate_links = 0
        for link in links:
            if link in all_links:
                duplicate_links += 1
            else:
                all_links.add(link)
                new_links += 1

        audit.record_page(
            current_page,
            links_count=len(links),
            new_links_count=new_links,
            duplicate_links_count=duplicate_links,
        )

        print(f"[INFO] Links encontrados en esta página: {len(links)}")
        print(f"[INFO] Links nuevos en esta página: {new_links}")
        print(f"[INFO] Links repetidos en esta página: {duplicate_links}")
        print(f"[INFO] Links acumulados: {len(all_links)}")

    return list(all_links), audit


# ==========================================================
# EXTRACCIÓN DE CADA PUBLICACIÓN
# ==========================================================

def extract_publication_data(page, url, fuente_id):
    print(f"[INFO] Extrayendo publicación: {url}")

    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(DETAIL_LOAD_WAIT_MS)

    html = page.content()
    text = page.locator("body").inner_text(timeout=15000)
    lines = get_lines(text)

    try:
        title = clean_text(page.locator("h1").first.inner_text(timeout=5000))
    except Exception:
        title = None

    codigo_externo = extract_codigo(text)
    precio = extract_precio(text)

    if not precio or precio <= 0:
        print(f"[WARN] Publicación omitida por precio inválido: {url}")
        return None, html

    ciudad, barrio, direccion = extract_location(
        lines=lines,
        title=title,
        text=text
    )

    coordenadas, latitud, longitud = extract_coordinates_from_source(
        html=html,
        text=text
    )

    area_privada = value_after_label(lines, "Área privada")
    area_construida = value_after_label(lines, "Área construida")

    m2 = parse_decimal(area_privada)
    m2_construido = parse_decimal(area_construida)

    habitaciones = extract_number_by_keywords(
        text,
        ["Habitaciones", "Alcobas"]
    )

    banios = extract_number_by_keywords(
        text,
        ["Baños", "Banos", "Baño", "Bano"]
    )

    parqueadero = extract_number_by_keywords(
        text,
        ["Parqueaderos", "Parqueadero", "Garajes", "Garaje"]
    )

    estrato = parse_int(value_after_label(lines, "Estrato"))
    antiguedad = value_after_label(lines, "Antigüedad")

    descripcion = extract_section(
        lines,
        "Descripción",
        [
            "Zonas comunes",
            "Explorar cercanías",
            "¿Aún tienes dudas?",
            "Contactar vendedor",
            "Características",
            "Gastos",
            "Calcula tu crédito"
        ]
    )

    tipo_inmueble = extract_tipo_inmueble(title, text)
    ph = extract_ph(descripcion)
    pisos = extract_pisos(descripcion)
    administracion = extract_administracion(text)

    direccion = direccion or ", ".join(
        [value for value in [barrio, ciudad or "Pasto", "Nariño"] if value]
    )
    direccion = clean_text(direccion)

    links_adicionales = {
        "fuente_busqueda": SEARCH_URL,
        "maps": None
    }

    data = {
        "fuente_id": fuente_id,
        "codigo_externo": codigo_externo,
        "link_origen": url,
        "links_adicionales": json.dumps(links_adicionales, ensure_ascii=False),
        "coordenadas": coordenadas,
        "latitud": latitud,
        "longitud": longitud,
        "direccion": direccion,
        "ciudad": ciudad or "Pasto",
        "barrio": barrio,
        "tipo_inmueble": tipo_inmueble,
        "ph": ph,
        "estrato": estrato,
        "descripcion": descripcion,
        "precio": precio,
        "m2": m2,
        "m2_construido": m2_construido,
        "antiguedad": antiguedad,
        "pisos": pisos,
        "habitaciones": habitaciones,
        "banios": banios,
        "parqueadero": parqueadero,
        "administracion": administracion,
        "notas": None
    }

    return data, html


# ==========================================================
# PROCESO PRINCIPAL
# ==========================================================

def main():
    print("[INFO] Iniciando scraper Ciencuadras Pasto")
    print(f"[INFO] HEADLESS: {HEADLESS}")
    print(f"[INFO] MAX_PAGES: {MAX_PAGES}")

    connection = get_connection()
    fuente_id = get_or_create_fuente_id(connection)

    total_nuevas = 0
    total_saltadas = 0
    total_errores = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=HEADLESS
        )

        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        publication_links, audit = collect_publication_links(page)

        print(f"[INFO] Total publicaciones encontradas: {len(publication_links)}")

        for index, link in enumerate(publication_links, start=1):
            print(f"\n[INFO] Procesando {index}/{len(publication_links)}")
            print(f"[INFO] Link: {link}")

            try:
                publicacion_existente_id = publicacion_ya_existe(connection, link)

                if publicacion_existente_id:
                    total_saltadas += 1
                    print(f"[SKIP] Ya existe en base de datos. ID {publicacion_existente_id}")
                    continue

                data, html = extract_publication_data(page, link, fuente_id)

                if not data:
                    total_errores += 1
                    audit.record_omission("sin_datos_extraidos_o_sin_precio", link)
                    continue

                try:
                    publicacion_id = insert_publicacion(connection, data)
                except IntegrityError:
                    publicacion_existente_id = publicacion_ya_existe(connection, link)

                    if publicacion_existente_id:
                        total_saltadas += 1
                        print(f"[SKIP] Ya existía al momento de insertar. ID {publicacion_existente_id}")
                        continue

                    raise

                total_nuevas += 1

                codigo_archivo = data["codigo_externo"] or f"publicacion_{publicacion_id}"

                html_path = save_html(
                    html=html,
                    codigo_archivo=codigo_archivo,
                    publicacion_id=publicacion_id
                )

                insert_evidencia(
                    connection=connection,
                    publicacion_id=publicacion_id,
                    tipo="html",
                    ruta_archivo=html_path,
                    url_original=link
                )

                screenshot_path = save_screenshot(
                    page=page,
                    codigo_archivo=codigo_archivo,
                    publicacion_id=publicacion_id
                )

                if screenshot_path:
                    insert_evidencia(
                        connection=connection,
                        publicacion_id=publicacion_id,
                        tipo="screenshot",
                        ruta_archivo=screenshot_path,
                        url_original=link
                    )

                image_urls = collect_image_urls(page)

                if not image_urls:
                    print("[WARN] No se detectaron fotos para descargar.")

                downloaded_images = download_images_parallel(
                    image_urls=image_urls,
                    codigo_archivo=codigo_archivo,
                    publicacion_id=publicacion_id
                )

                for _, image_url, image_path in downloaded_images:
                    insert_evidencia(
                        connection=connection,
                        publicacion_id=publicacion_id,
                        tipo="imagen",
                        ruta_archivo=image_path,
                        url_original=image_url
                    )

                print(f"[OK] Guardada publicación nueva ID {publicacion_id}")
                print(f"[OK] Código externo: {data['codigo_externo']}")
                print(f"[OK] Dirección: {data['direccion']}")
                print(f"[OK] Barrio: {data['barrio']}")
                print(f"[OK] Precio: {data['precio']}")
                print(f"[OK] Coordenadas: {data['coordenadas']}")
                print(f"[OK] Carpeta evidencias: evidencias/publicacion_{publicacion_id}")

                if REQUEST_PAUSE_SECONDS > 0:
                    time.sleep(REQUEST_PAUSE_SECONDS)

            except Exception as error:
                total_errores += 1
                audit.record_error(link, error)
                print(f"[ERROR] Falló publicación {link}: {error}")
                continue

        browser.close()

    connection.close()

    print("\n[OK] Scraping finalizado.")
    print(f"[RESUMEN] Nuevas guardadas: {total_nuevas}")
    print(f"[RESUMEN] Saltadas porque ya existían: {total_saltadas}")
    print(f"[RESUMEN] Errores u omitidas: {total_errores}")
    audit.set_processing_counts(
        nuevas=total_nuevas,
        saltadas=total_saltadas,
        errores_u_omitidas=total_errores,
    )
    audit.print_summary(len(publication_links))
    audit.save(len(publication_links))


if __name__ == "__main__":
    main()
