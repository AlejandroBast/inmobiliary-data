import os
import re
import json
import time
import math
import html as html_module
import requests
import mysql.connector

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv
from mysql.connector import IntegrityError
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from inmobiliary.detectors.duplicates import detect_duplicates_safely
import inmobiliary.common as common
from inmobiliary.detectors.location import location_diagnostic, resolve_pasto_location
from inmobiliary.net import with_retry
from inmobiliary.common import (
    clean_text,
    get_connection,
    get_lines,
    insert_evidencia,
    only_digits,
    parse_int,
    publicacion_ya_existe,
    sanitize_filename,
)
from inmobiliary.detectors.ph import detect_ph
from inmobiliary.audit import ScraperAudit


# ==========================================================
# CONFIGURACIÓN GENERAL
# ==========================================================

load_dotenv()

SEARCH_URL = os.getenv(
    "FINCARAIZ_SEARCH_URL",
    "https://www.fincaraiz.com.co/venta/pasto/narino"
)
BASE_URL = "https://www.fincaraiz.com.co"

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
# 0 = recorrer todas las paginas detectadas por el contador del sitio.
MAX_PAGES = int(os.getenv("MAX_PAGES", "0"))

SEARCH_LOAD_WAIT_MS = int(os.getenv("SEARCH_LOAD_WAIT_MS", "2500"))
DETAIL_LOAD_WAIT_MS = int(os.getenv("DETAIL_LOAD_WAIT_MS", "1400"))
SCROLL_WAIT_MS = int(os.getenv("SCROLL_WAIT_MS", "900"))
REQUEST_PAUSE_SECONDS = float(os.getenv("REQUEST_PAUSE_SECONDS", "0.5"))

IMAGE_DOWNLOAD_WORKERS = int(os.getenv("IMAGE_DOWNLOAD_WORKERS", "6"))
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "12"))

# Área mínima (ancho*alto) para considerar que una imagen es una foto real
# de la publicación y no un ícono/logo/thumbnail de UI.
MIN_PHOTO_AREA = int(os.getenv("MIN_PHOTO_AREA", str(150 * 150)))

EVIDENCE_DIR = Path("evidencias")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def get_publication_evidence_dirs(publicacion_id):
    return common.get_publication_evidence_dirs(publicacion_id, EVIDENCE_DIR)


def get_or_create_fuente_id(connection):
    return common.get_or_create_fuente_id(
        connection,
        "Fincaraiz",
        BASE_URL,
        "portal",
        "Scraper de inmuebles en venta en Pasto desde Fincaraiz",
    )



# ==========================================================
# UTILIDADES
# ==========================================================

def parse_colombian_decimal(value):
    """
    Convierte textos como:
    - 100 m2      -> 100
    - 47.1 m²     -> 47.1
    - 118.65 m2   -> 118.65
    - 1.104 m2    -> 1104
    - 1,104 m2    -> 1.104
    """
    if not value:
        return None

    text = str(value).lower()
    match = re.search(r"(\d+(?:[\.,]\d+)*)", text)

    if not match:
        return None

    number = match.group(1)

    if "," in number and "." in number:
        # Formato colombiano: 1.234,56
        number = number.replace(".", "").replace(",", ".")
    elif "," in number:
        number = number.replace(",", ".")
    elif "." in number:
        parts = number.split(".")

        # 1.104 normalmente significa mil ciento cuatro.
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 2:
            number = "".join(parts)
        else:
            number = number

    try:
        return float(number)
    except ValueError:
        return None


def normalize_label(value):
    value = clean_text(value) or ""
    value = value.lower()
    value = value.replace(":", "")
    value = value.replace("á", "a").replace("é", "e").replace("í", "i")
    value = value.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def value_after_label(lines, label, max_lookahead=5):
    """
    Fincaraíz suele traer los detalles así:
    Baños
    2
    Habitaciones
    3
    Área Construida
    100 m2
    """
    label_normalized = normalize_label(label)

    for index, line in enumerate(lines):
        line_normalized = normalize_label(line)

        if line_normalized == label_normalized or line_normalized.startswith(label_normalized):
            if ":" in line:
                possible_value = line.split(":", 1)[1].strip()

                if possible_value:
                    return clean_text(possible_value)

            for next_index in range(index + 1, min(index + max_lookahead + 1, len(lines))):
                next_line = clean_text(lines[next_index])
                next_normalized = normalize_label(next_line)

                if not next_line:
                    continue

                # Evita devolver separadores o labels cercanos.
                if next_normalized in ["•", "detalles de la propiedad", label_normalized]:
                    continue

                return next_line

    return None


def extract_section(lines, start_label, stop_labels):
    start_normalized = normalize_label(start_label)
    stop_normalized = [normalize_label(label) for label in stop_labels]
    start_index = None

    for index, line in enumerate(lines):
        if normalize_label(line) == start_normalized:
            start_index = index + 1
            break

    if start_index is None:
        return None

    content = []

    for line in lines[start_index:]:
        line_normalized = normalize_label(line)

        if any(line_normalized.startswith(stop) for stop in stop_normalized):
            break

        content.append(line)

    return clean_text(" ".join(content))


# ==========================================================
# EXTRACCIÓN DE DATOS FINCARAÍZ
# ==========================================================

TIPOS_INMUEBLE = [
    "Apartamento",
    "Casa Lote",
    "Casa",
    "Lote",
    "Oficina",
    "Local",
    "Apartaestudio",
    "Edificio",
    "Consultorio",
    "Finca",
    "Bodega"
]


def extract_title_parts(title):
    """
    Ejemplo:
    Casa en Venta en San fernando, Pasto
    Apartamento en venta en la colina, pasto
    """
    title = clean_text(title)

    if not title:
        return None, None

    tipo_inmueble = None

    for tipo in TIPOS_INMUEBLE:
        if re.search(rf"\b{re.escape(tipo)}\b", title, re.IGNORECASE):
            tipo_inmueble = tipo
            break

    barrio = None

    patterns = [
        r"en\s+venta\s+en\s+(.+?),\s*pasto",
        r"en\s+(.+?),\s*pasto",
    ]

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)

        if match:
            barrio = clean_text(match.group(1))
            break

    return tipo_inmueble, barrio


def extract_total_results(text):
    if not text:
        return None

    patterns = [
        r"Mostrando\s+\d+\s*-\s*\d+\s+de\s+([\d\.,]+)\s+resultados",
        r"de\s+([\d\.,]+)\s+resultados",
        r"([\d\.,]+)\s+resultados"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return only_digits(match.group(1))

    return None


def extract_result_window(text):
    if not text:
        return None

    patterns = [
        r"Mostrando\s+([\d\.,]+)\s*[-\u2013]\s*([\d\.,]+)\s+de\s+([\d\.,]+)\s+resultados",
        r"([\d\.,]+)\s*[-\u2013]\s*([\d\.,]+)\s+de\s+([\d\.,]+)\s+resultados",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = only_digits(match.group(1))
            end = only_digits(match.group(2))
            total = only_digits(match.group(3))
            if start and end and total and end >= start:
                return start, end, total

    return None


def extract_codigo(text, url=None):
    source = text or ""

    patterns = [
        r"Código\s+Fincara[íi]z\s*:\s*([A-Za-z0-9\-]+)",
        r"Código\s*:\s*([A-Za-z0-9\-]+)",
        r"Cod\.?\s*:\s*([A-Za-z0-9\-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, source, re.IGNORECASE)

        if match:
            return clean_text(match.group(1))

    if url:
        path = urlparse(url).path.strip("/")
        last_part = path.split("/")[-1]

        if re.fullmatch(r"\d+", last_part):
            return last_part

    return None


def extract_precio(text):
    if not text:
        return None

    patterns = [
        r"\$\s*([\d\.]{5,})\s*(?:Precio\s+de\s+Venta)?",
        r"Precio\s+de\s+Venta\s*\$?\s*([\d\.]{5,})",
        r"Valor\s+de\s+venta\s*:\s*\$?\s*([\d\.]{5,})",
        r"Venta\s+es\s+de\s+\$\s*([\d\.]{5,})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return only_digits(match.group(1))

    return None


def extract_number_by_label(lines, *labels):
    for label in labels:
        value = value_after_label(lines, label)
        number = parse_int(value)

        if number is not None:
            return number

    return None


def extract_area_by_label(lines, *labels):
    for label in labels:
        value = value_after_label(lines, label)
        number = parse_colombian_decimal(value)

        if number is not None:
            return number

    return None


def first_json_value(data, path):
    current = data

    for key in path:
        if isinstance(current, list):
            current = current[0] if current else None

        if not isinstance(current, dict):
            return None

        current = current.get(key)

    if isinstance(current, list):
        current = current[0] if current else None

    return clean_text(current) if isinstance(current, str) else None


def extract_embedded_property_data(html):
    if not html:
        return {}

    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE
    )

    if not match:
        return {}

    try:
        next_data = json.loads(html_module.unescape(match.group(1)))
    except Exception:
        return {}

    data = next_data.get("props", {}).get("pageProps", {}).get("data", {})
    return data if isinstance(data, dict) else {}


def extract_barrio_from_address(address):
    address = clean_text(address)

    if not address:
        return None

    match = re.search(
        r"\bBarrio\s+([A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s\.\-]+?)(?:\s{2,}|,|\.|$|\s+Estrato\b|\s+Ubicaci[oó]n\b|\s+Deposito\b|\s+Garaje\b)",
        address,
        re.IGNORECASE
    )

    if not match:
        return None

    barrio = clean_text(match.group(1))

    if not barrio or barrio in ["-", "N/A"]:
        return None

    return barrio.title()


def extract_structured_location(html):
    data = extract_embedded_property_data(html)

    # location_main es la ubicacion propia de la ficha (autoritativa). El campo
    # neighbourhood es una lista de barrios cercanos: tomar su [0] podia devolver
    # un barrio vecino en vez del de la publicacion.
    main = first_json_value(data, ["locations", "location_main", "name"])
    if main:
        return main, first_json_value(data, ["address"])

    neighbourhood = first_json_value(data, ["locations", "neighbourhood", "name"])
    if neighbourhood:
        return neighbourhood, first_json_value(data, ["address"])

    address = first_json_value(data, ["address"])
    return extract_barrio_from_address(address), address


def extract_location(lines, title=None, text=None, html=None):
    _, title_barrio = extract_title_parts(title)

    location_values = []
    structured_barrio, structured_address = extract_structured_location(html)

    if structured_barrio:
        location_values.append(f"{structured_barrio}, Pasto, Nariño")

    ubicacion_principal = value_after_label(lines, "Ubicación Principal", max_lookahead=3)
    if ubicacion_principal:
        location_values.append(ubicacion_principal)

    ubicacion = value_after_label(lines, "Ubicación", max_lookahead=3)
    if ubicacion:
        location_values.append(ubicacion)

    if title_barrio:
        location_values.append(f"{title_barrio}, Pasto, Nariño")

    full_text = " ".join([title or "", text or ""])
    match = re.search(r"([A-Za-zÁÉÍÓÚÑáéíóúñ\s\.]+),\s*Pasto,\s*Nariño", full_text, re.IGNORECASE)

    if match:
        location_values.append(match.group(0))

    for location in location_values:
        location = clean_text(location)

        if not location:
            continue

        parts = [clean_text(part) for part in location.split(",") if clean_text(part)]
        barrio = None
        ciudad = "Pasto"

        for part in parts:
            part_normalized = normalize_label(part)

            if part_normalized not in ["pasto", "narino"]:
                barrio = part
                break

        direccion = clean_text(", ".join([value for value in [barrio, ciudad, "Nariño"] if value]))

        return ciudad, barrio, direccion

    if structured_address:
        return "Pasto", None, structured_address

    return "Pasto", None, "Pasto, Nariño"


def is_pasto_publication(url, title=None, html=None):
    """Exige una señal territorial en la identidad oficial de la ficha."""
    head = (html or "").split("</head>", 1)[0]
    official_identity = normalize_label(" ".join([url or "", title or "", head]))
    return re.search(r"\bpasto\b", official_identity, re.IGNORECASE) is not None


def extract_tipo_inmueble(title, lines, text):
    value = value_after_label(lines, "Tipo de Inmueble")

    if value:
        value_clean = clean_text(value)

        for tipo in TIPOS_INMUEBLE:
            if re.search(rf"\b{re.escape(tipo)}\b", value_clean, re.IGNORECASE):
                return tipo

        return value_clean

    title_tipo, _ = extract_title_parts(title)

    if title_tipo:
        return title_tipo

    source = f"{title or ''} {text or ''}".lower()

    for tipo in TIPOS_INMUEBLE:
        if tipo.lower() in source:
            return tipo

    return None


def extract_estrato(lines):
    value = value_after_label(lines, "Estrato")

    if not value:
        return None

    if "sin definir" in value.lower() or "preg" in value.lower():
        return None

    return parse_int(value)


def extract_pisos(lines, description):
    value = value_after_label(lines, "Cantidad de pisos")
    pisos = parse_int(value)

    if pisos is not None:
        return pisos

    if description:
        match = re.search(r"(\d+)\s*(pisos|piso|niveles|nivel)", description, re.IGNORECASE)

        if match:
            return int(match.group(1))

    return None


def extract_administracion(lines, text):
    value = value_after_label(lines, "Administración")

    if value:
        amount = only_digits(value)

        if amount:
            return amount

    patterns = [
        r"\+\s*\$\s*([\d\.]+)\s*admin",
        r"administraci[oó]n\s*[:\$]?\s*([\d\.]+)",
        r"vigilancia\s*[:\$]?\s*([\d\.]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)

        if match:
            amount = only_digits(match.group(1))

            if amount:
                return amount

    return None


def extract_ph(description):
    # Deteccion centralizada en ph_detector: ademas del nombre propio
    # (Conjunto/Edificio/Condominio/Urbanizacion/Torres) que ya se buscaba
    # aqui, ahora tambien reconoce menciones sueltas (PH, Propiedad
    # Horizontal, administracion incluida) que antes esta funcion no capturaba.
    return detect_ph(description)


def valid_colombia_coordinates(latitud, longitud):
    return latitud is not None and longitud is not None and -5 <= latitud <= 15 and -82 <= longitud <= -66


def coordinate_float(value):
    if value is None:
        return None

    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def coordinate_result(latitud, longitud):
    latitud = coordinate_float(latitud)
    longitud = coordinate_float(longitud)

    if valid_colombia_coordinates(latitud, longitud):
        return f"{latitud},{longitud}", latitud, longitud

    return None


def find_coordinates_in_data(value):
    if isinstance(value, dict):
        latitude = (
            value.get("latitude")
            or value.get("latitud")
            or value.get("lat")
        )
        longitude = (
            value.get("longitude")
            or value.get("longitud")
            or value.get("lng")
            or value.get("lon")
            or value.get("long")
        )

        result = coordinate_result(latitude, longitude)
        if result:
            return result

        coordinates = value.get("coordinates") or value.get("coordenadas")

        if isinstance(coordinates, list) and len(coordinates) >= 2:
            first = coordinate_float(coordinates[0])
            second = coordinate_float(coordinates[1])

            result = coordinate_result(second, first)
            if result:
                return result

            result = coordinate_result(first, second)
            if result:
                return result

        if isinstance(coordinates, str):
            match = re.search(r"(-?\d+(?:[\.,]\d+)?)\s*,\s*(-?\d+(?:[\.,]\d+)?)", coordinates)

            if match:
                result = coordinate_result(match.group(1), match.group(2))
                if result:
                    return result

        for nested_value in value.values():
            result = find_coordinates_in_data(nested_value)
            if result:
                return result

    if isinstance(value, list):
        for item in value:
            result = find_coordinates_in_data(item)
            if result:
                return result

    return None


def extract_coordinates_from_source(html, text):
    structured_result = find_coordinates_in_data(extract_embedded_property_data(html))

    if structured_result:
        return structured_result

    source = f"{html or ''}\n{text or ''}"

    patterns = [
        r'"latitude"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?.*?"longitude"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?',
        r'"latitud"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?.*?"longitud"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?',
        r'"lat"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?.*?"lng"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?',
        r'"lat"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?.*?"lon"\s*:\s*"?(-?\d+(?:[\.,]\d+)?)"?',
        r'data-lat\s*=\s*["\'](-?\d+(?:[\.,]\d+)?)["\'].*?data-lng\s*=\s*["\'](-?\d+(?:[\.,]\d+)?)["\']',
        r'coordenadas?\s*[:=]\s*(-?\d+(?:[\.,]\d+)?)\s*,\s*(-?\d+(?:[\.,]\d+)?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)

        if match:
            result = coordinate_result(match.group(1), match.group(2))

            if result:
                return result

    geojson_match = re.search(
        r'"coordinates"\s*:\s*\[\s*"?(-?\d+(?:[\.,]\d+)?)"?\s*,\s*"?(-?\d+(?:[\.,]\d+)?)"?\s*\]',
        source,
        re.IGNORECASE
    )

    if geojson_match:
        result = coordinate_result(geojson_match.group(2), geojson_match.group(1))

        if result:
            return result

    return None, None, None


# ==========================================================
# BASE DE DATOS
# ==========================================================

def insert_publicacion(connection, data):
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


def update_existing_coordinates(connection, publicacion_id, data):
    if not data.get("coordenadas") and not (data.get("latitud") and data.get("longitud")):
        return False

    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE publicaciones
        SET
            coordenadas = COALESCE(NULLIF(coordenadas, ''), %s),
            latitud = COALESCE(latitud, %s),
            longitud = COALESCE(longitud, %s)
        WHERE id = %s
          AND (
              coordenadas IS NULL OR TRIM(coordenadas) = ''
              OR latitud IS NULL
              OR longitud IS NULL
          )
        """,
        (
            data.get("coordenadas"),
            data.get("latitud"),
            data.get("longitud"),
            publicacion_id
        )
    )
    connection.commit()
    updated = cursor.rowcount > 0
    cursor.close()

    return updated


# ==========================================================
# EVIDENCIAS POR ID DE PUBLICACIÓN
# ==========================================================

def save_html(html, codigo_archivo, publicacion_id):
    html_dir, _, _ = get_publication_evidence_dirs(publicacion_id)

    filename = f"fincaraiz_{sanitize_filename(codigo_archivo)}.html"
    path = html_dir / filename

    with open(path, "w", encoding="utf-8") as file:
        file.write(html)

    return path


def save_screenshot(page, codigo_archivo, publicacion_id):
    _, _, screenshot_dir = get_publication_evidence_dirs(publicacion_id)

    filename = f"fincaraiz_{sanitize_filename(codigo_archivo)}.png"
    path = screenshot_dir / filename

    try:
        page.screenshot(path=str(path), full_page=True)
        return path
    except Exception as error:
        print(f"[WARN] No se pudo guardar screenshot: {error}")
        return None


# ==========================================================
# COLECCIÓN DE IMÁGENES (FIX: solo fotos reales de la publicación)
# ==========================================================
#
# Confirmado con HTML real del sitio: las fotos de la publicación viven
# dentro del contenedor .property-modal-photos, en elementos .pmp-image > img.
# Ejemplo real:
# <div class="property-modal-photos ..."><div class="pmp-image">
#   <img src="https://cdn4.fincaraiz.com.co/repo/img/th.outside500x500...jpeg"
#        width="500" height="500"></div></div>
#
# El bug anterior usaba selectores genéricos ([class*='modal'],
# [class*='gallery'], [class*='carousel']) que también capturan otros
# modales/carruseles de la página (contacto, cookies, recomendados, etc.),
# colando íconos y logos junto a las fotos reales.

IMAGE_URL_COLLECTOR_JS = r"""
containers => {
    const urls = [];

    const addCandidate = (candidates, value) => {
        if (!value) return;

        String(value)
            .split(',')
            .map(item => item.trim().split(/\s+/)[0])
            .filter(Boolean)
            .forEach(url => candidates.push(url));
    };

    const isBlockedImage = (url) => {
        const lower = String(url).toLowerCase();

        return lower.startsWith('data:')
            || lower.includes('.svg')
            || lower.includes('tile.openstreetmap.org')
            || lower.includes('/web/')
            || lower.includes('/icons/')
            || lower.includes('logo')
            || lower.includes('app_store')
            || lower.includes('google-play')
            || lower.includes('appgallery')
            || lower.includes('placeholder')
            || lower.includes('avatar')
            || lower.includes('sprite');
    };

    const collectFromElement = (element) => {
        const candidates = [];

        addCandidate(candidates, element.getAttribute('data-src'));
        addCandidate(candidates, element.getAttribute('lazyload'));
        addCandidate(candidates, element.getAttribute('srcset'));
        addCandidate(candidates, element.getAttribute('src'));
        addCandidate(candidates, element.currentSrc);

        // Señal extra: dimensiones declaradas en los atributos width/height
        // del propio <img>, que en Fincaraíz son fiables para las fotos
        // reales de la publicación (ej. width="500" height="500").
        // Nota: si el atributo no existe o no es numérico, parseInt puede
        // devolver NaN. Se normaliza a 0 aquí mismo para que nunca viaje
        // un NaN hacia Python (Playwright sí puede serializarlo, y un NaN
        // ahí rompe cualquier int(width) más adelante).
        const parsedWidth = parseInt(element.getAttribute('width') || '0', 10);
        const parsedHeight = parseInt(element.getAttribute('height') || '0', 10);
        const width = Number.isFinite(parsedWidth) ? parsedWidth : 0;
        const height = Number.isFinite(parsedHeight) ? parsedHeight : 0;

        candidates
            .filter(url => !isBlockedImage(url))
            .forEach(url => urls.push({ url, width, height }));
    };

    containers.forEach(container => {
        container.querySelectorAll('picture').forEach(picture => {
            picture.querySelectorAll('source, img').forEach(element => collectFromElement(element));
        });

        container.querySelectorAll('source, img').forEach(element => {
            if (element.closest('picture')) return;
            collectFromElement(element);
        });

        container.querySelectorAll('[style*="background-image"]').forEach(element => {
            const style = element.getAttribute('style') || '';
            const matches = Array.from(style.matchAll(/url\(["']?([^"')]+)["']?\)/gi));

            matches.forEach(match => {
                if (match[1] && !isBlockedImage(match[1])) {
                    urls.push({ url: match[1], width: 0, height: 0 });
                }
            });
        });
    });

    // Deduplicar preservando la primera aparición.
    const seen = new Set();
    const result = [];

    urls.forEach(item => {
        if (!seen.has(item.url)) {
            seen.add(item.url);
            result.push(item);
        }
    });

    return result;
}
"""


def image_identity(image_url):
    match = re.search(r"_infocdn__([^/?#]+)", image_url, re.IGNORECASE)

    if match:
        return match.group(1).lower()

    return image_url.lower()


def _safe_dimension(value):
    """
    Convierte a int de forma segura. Devuelve 0 si el valor es None, NaN,
    o cualquier cosa no convertible (protección extra por si algún dato
    llega en un formato inesperado desde el navegador).
    """
    if value is None:
        return 0

    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0

    if math.isnan(number) or math.isinf(number):
        return 0

    return int(number)


def image_resolution_score(image_url, width=0, height=0):
    width = _safe_dimension(width)
    height = _safe_dimension(height)

    if width and height:
        return width * height

    match = re.search(r"(\d+)x(\d+)", image_url)

    if not match:
        return 0

    return int(match.group(1)) * int(match.group(2))


def normalize_image_urls(image_items):
    """
    image_items: lista de dicts {"url": str, "width": int, "height": int}
    (o strings simples, por compatibilidad hacia atrás).
    """
    cleaned = []
    positions_by_identity = {}

    for item in image_items or []:
        if isinstance(item, dict):
            raw_url = item.get("url")
            width = item.get("width") or 0
            height = item.get("height") or 0
        else:
            raw_url = item
            width = 0
            height = 0

        if not raw_url or not str(raw_url).strip():
            continue

        image_url = urljoin(BASE_URL, str(raw_url).strip())
        lower = image_url.lower()

        if lower.startswith("data:"):
            continue

        # Las fotos reales de la publicación siempre vienen de este path del CDN.
        if "/repo/img/" not in lower:
            continue

        if any(blocked in lower for blocked in [
            ".svg",
            "tile.openstreetmap.org",
            "/web/",
            "/icons/",
            "logo",
            "placeholder",
            "avatar",
            "google-play",
            "app_store",
            "appgallery",
            "sprite"
        ]):
            continue

        # Filtro por tamaño: descarta íconos/miniaturas de UI que se hayan
        # colado aunque vengan del mismo CDN (ej. thumbnails muy pequeños).
        resolution_score = image_resolution_score(image_url, width, height)

        if resolution_score and resolution_score < MIN_PHOTO_AREA:
            continue

        identity = image_identity(image_url)

        if identity in positions_by_identity:
            position = positions_by_identity[identity]
            current_url = cleaned[position]

            if image_resolution_score(image_url, width, height) > image_resolution_score(current_url):
                cleaned[position] = image_url

            continue

        positions_by_identity[identity] = len(cleaned)
        cleaned.append(image_url)

    return cleaned


def open_gallery(page):
    gallery_selectors = [
        "button:has-text('Galer')",
        "[role='button']:has-text('Galer')",
        "text=Galer",
    ]

    for selector in gallery_selectors:
        try:
            element = page.locator(selector).first

            if element.count() == 0:
                continue

            element.click(timeout=5000)
            page.wait_for_timeout(1200)
            print("[INFO] Galeria extendida abierta para buscar mas fotos.")
            return True
        except Exception:
            continue

    return False


def collect_gallery_image_urls(page):
    """
    FIX: apunta específicamente a .property-modal-photos (confirmado con
    HTML real del sitio), en vez de selectores genéricos de "cualquier
    modal/carrusel/galería" que también capturan otros componentes de la
    página (contacto, cookies, recomendados, etc.).
    """
    gallery_selector = ".property-modal-photos"

    image_items = []

    for _ in range(4):
        try:
            image_items.extend(page.eval_on_selector_all(gallery_selector, IMAGE_URL_COLLECTOR_JS))
        except Exception:
            pass

        try:
            page.evaluate(
                """
                () => {
                    const container = document.querySelector('.property-modal-photos');
                    if (container) {
                        container.scrollTop = container.scrollHeight;
                    }
                }
                """
            )
            page.wait_for_timeout(500)
        except Exception:
            break

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass

    return image_items


def collect_image_urls(page):
    try:
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)
    except Exception:
        pass

    # Selectores de portada (antes de abrir la galería completa).
    selectors = (
        ".property-cover-gallery, "
        ".property_details_cover, "
        ".pd-property-cover-col, "
        "[class*='property-cover-gallery'], "
        "[class*='property_details_cover']"
    )

    try:
        image_items = page.eval_on_selector_all(selectors, IMAGE_URL_COLLECTOR_JS)
    except Exception:
        image_items = []

    if open_gallery(page):
        image_items.extend(collect_gallery_image_urls(page))

    image_urls = normalize_image_urls(image_items)

    print(f"[INFO] Fotos detectadas para descargar: {len(image_urls)}")

    return image_urls


def download_image(image_url, codigo_archivo, index, publicacion_id):
    _, img_dir, _ = get_publication_evidence_dirs(publicacion_id)

    try:
        def fetch_image():
            response = requests.get(
                image_url,
                timeout=IMAGE_DOWNLOAD_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            response.raise_for_status()
            return response

        response = with_retry(fetch_image, f"Descargar imagen {image_url}")

        content_type = response.headers.get("Content-Type", "").lower()

        if "png" in content_type:
            extension = ".png"
        elif "webp" in content_type:
            extension = ".webp"
        else:
            extension = ".jpg"

        filename = f"fincaraiz_{sanitize_filename(codigo_archivo)}_{index}{extension}"
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
# LINKS Y PAGINACIÓN FINCARAÍZ
# ==========================================================

def build_search_page_url(page_number):
    if page_number <= 1:
        return SEARCH_URL

    return f"{SEARCH_URL.rstrip('/')}/pagina{page_number}"


def get_current_page_links(page):
    try:
        links = page.eval_on_selector_all(
            "a[href]",
            r"""
            anchors => anchors
                .map(a => a.href)
                .filter(Boolean)
                .map(href => href.split('?')[0].split('#')[0])
                .filter(href => {
                    try {
                        const url = new URL(href);
                        const path = url.pathname.toLowerCase();

                        return url.hostname.includes('fincaraiz.com.co')
                            && /\/\d{6,}$/.test(path)
                            && path.includes('en-venta');
                    } catch (error) {
                        return false;
                    }
                })
            """
        )

        return list(dict.fromkeys(links))

    except Exception:
        return []


def get_max_page_from_pagination(page, search_url):
    """
    FIX: en vez de inferir el número de páginas solo por matemática
    (total_resultados / resultados_por_pagina), se lee directamente del DOM
    el número máximo de página real, a partir de los propios links de
    paginación del sitio (ej. .../pagina2, .../pagina3 ... .../pagina8).
    Esto evita quedarse corto si el tamaño de página no es constante.
    """
    base = search_url.rstrip("/")

    try:
        hrefs = page.eval_on_selector_all(
            "a[href]",
            "anchors => anchors.map(a => a.href).filter(Boolean)"
        )
    except Exception:
        return None

    max_page = None
    pattern = re.compile(re.escape(base) + r"/pagina(\d+)$", re.IGNORECASE)

    for href in hrefs:
        match = pattern.search(href.split("?")[0].split("#")[0])

        if match:
            page_number = int(match.group(1))

            if max_page is None or page_number > max_page:
                max_page = page_number

    return max_page


def collect_publication_links(page):
    audit = ScraperAudit("FincaRaiz", SEARCH_URL)
    all_links = set()

    first_url = build_search_page_url(1)
    try:
        with_retry(
            lambda: page.goto(first_url, wait_until="domcontentloaded", timeout=60000),
            "Abrir primera pagina de resultados",
        )
    except Exception as error:
        reason = f"No se pudo abrir la primera pagina de resultados: {error}"
        print(f"[ERROR] {reason}")
        audit.record_page(1, url=first_url, status="error", reason=reason)
        return [], audit

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(SEARCH_LOAD_WAIT_MS)

    body_text = page.locator("body").inner_text(timeout=15000)
    total_results = extract_total_results(body_text)
    result_window = extract_result_window(body_text)

    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(SCROLL_WAIT_MS)
    except Exception:
        pass

    first_page_links = get_current_page_links(page)

    # FUENTE PRIMARIA: número de página real leído del DOM (paginación).
    pagination_max_page = get_max_page_from_pagination(page, SEARCH_URL)

    if result_window:
        start, end, window_total = result_window
        total_results = total_results or window_total
        page_size = max(end - start + 1, 1)
    else:
        page_size = len(first_page_links) or None

    if total_results and page_size:
        estimated_pages = math.ceil(total_results / page_size)
    else:
        estimated_pages = None

    if pagination_max_page:
        detected_pages = pagination_max_page
        if estimated_pages and estimated_pages != pagination_max_page:
            print(
                f"[WARN] La paginación del sitio indica {pagination_max_page} "
                f"pagina(s), pero el cálculo por resultados estimaba "
                f"{estimated_pages}. Se usa el valor real de la paginación."
            )
    elif estimated_pages:
        detected_pages = estimated_pages
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
    print(f"[INFO] Paginas segun paginación del sitio: {pagination_max_page}")
    print(f"[INFO] Limite MAX_PAGES: {MAX_PAGES if MAX_PAGES > 0 else 'sin limite'}")
    print(f"[INFO] Total páginas a revisar: {total_pages}")

    for current_page in range(1, total_pages + 1):
        search_page_url = build_search_page_url(current_page)

        print(f"[INFO] Revisando página {current_page} de {total_pages}")
        print(f"[INFO] URL listado: {search_page_url}")

        if current_page == 1:
            links = first_page_links
        else:
            try:
                with_retry(
                    lambda: page.goto(search_page_url, wait_until="domcontentloaded", timeout=60000),
                    f"Abrir pagina {current_page} de resultados",
                )
            except Exception as error:
                reason = f"No se pudo abrir la pagina {current_page}: {error}"
                print(f"[WARN] {reason}")
                audit.record_page(current_page, url=search_page_url, status="error", reason=reason)
                continue

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(SEARCH_LOAD_WAIT_MS)

            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(SCROLL_WAIT_MS)
            except Exception:
                pass

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
            url=search_page_url,
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

    with_retry(
        lambda: page.goto(url, wait_until="domcontentloaded", timeout=60000),
        f"Abrir publicación {url}",
    )

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

    if not is_pasto_publication(url=url, title=title, html=html):
        print(f"[SKIP] Publicacion fuera de Pasto: {url}")
        return None, html, "fuera_de_pasto"

    codigo_externo = extract_codigo(text, url=url)
    precio = extract_precio(text)

    if not precio or precio <= 0:
        print(f"[WARN] Publicación omitida por precio inválido: {url}")
        return None, html, "sin_precio"

    ciudad, barrio, direccion = extract_location(
        lines=lines,
        title=title,
        text=text,
        html=html
    )

    coordenadas, latitud, longitud = extract_coordinates_from_source(
        html=html,
        text=text
    )

    descripcion = extract_section(
        lines,
        "Descripción",
        [
            "Código Fincaraíz",
            "Completa tus datos",
            "Contactar",
            "Casa en Venta",
            "Apartamento en Venta",
            "Lote en Venta",
            "Estás en:",
            "Descarga la app"
        ]
    )

    tipo_inmueble = extract_tipo_inmueble(title, lines, text)

    m2_construido = extract_area_by_label(
        lines,
        "Área Construida",
        "Area Construida",
        "Área"
    )

    m2_privado = extract_area_by_label(
        lines,
        "Área Privada",
        "Area Privada",
        "Área del terreno",
        "Area del terreno"
    )

    # En tu base, m2 se puede usar como área privada/lote y m2_construido como área construida.
    m2 = m2_privado or m2_construido

    habitaciones = extract_number_by_label(lines, "Habitaciones", "Habs.", "Hab")
    banios = extract_number_by_label(lines, "Baños", "Baño", "Banos", "Bano")
    parqueadero = extract_number_by_label(lines, "Parqueaderos", "Parqueadero", "Garajes", "Garaje")

    estrato = extract_estrato(lines)
    antiguedad = value_after_label(lines, "Antigüedad") or value_after_label(lines, "Antiguedad")
    pisos = extract_pisos(lines, descripcion)
    administracion = extract_administracion(lines, text)
    ph = extract_ph(descripcion)

    location_result = resolve_pasto_location(
        barrio, title=title, description=descripcion, address=direccion, city=ciudad, ph=ph
    )
    print(f"[UBICACION] {location_diagnostic(location_result)}")
    if location_result.outside_municipality:
        return None, html, "fuera_de_pasto"
    barrio = location_result.value if location_result.accepted else None

    # Cuando la ubicacion propia de la ficha es un conjunto/edificio (Fincaraiz lo
    # entrega como su "barrio" pero el normalizador lo rechaza como propiedad
    # horizontal), ese es el nombre real del conjunto: se guarda en el campo ph,
    # que es su lugar correcto. Es mas fiable que el ph deducido del texto
    # publicitario de la descripcion.
    if location_result.kind == "propiedad horizontal" and location_result.original:
        ph = location_result.original

    direccion = direccion or clean_text(", ".join([value for value in [barrio, ciudad or "Pasto", "Nariño"] if value]))

    links_adicionales = {
        "fuente_busqueda": SEARCH_URL,
        "maps": None,
        "normalizacion_ubicacion": location_diagnostic(location_result),
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

    return data, html, None


# ==========================================================
# PROCESO PRINCIPAL
# ==========================================================

def main():
    print("[INFO] Iniciando scraper Fincaraíz Pasto")
    print(f"[INFO] SEARCH_URL: {SEARCH_URL}")
    print(f"[INFO] HEADLESS: {HEADLESS}")
    print(f"[INFO] MAX_PAGES: {MAX_PAGES}")

    connection = get_connection()
    fuente_id = get_or_create_fuente_id(connection)

    total_nuevas = 0
    total_saltadas = 0
    total_sin_precio = 0
    total_fuera_de_pasto = 0
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
                publicacion_existente_id_previo = publicacion_ya_existe(
                    connection=connection,
                    link_origen=link
                )

                data, html, skip_reason = extract_publication_data(page, link, fuente_id)

                if not data:
                    if skip_reason == "sin_precio":
                        total_sin_precio += 1
                        audit.record_omission("sin_precio", link)
                    elif skip_reason == "fuera_de_pasto":
                        total_fuera_de_pasto += 1
                        audit.record_omission("fuera_de_pasto", link)
                    else:
                        total_errores += 1
                        audit.record_omission("sin_datos_extraidos", link)
                    continue

                publicacion_existente_id = publicacion_existente_id_previo or publicacion_ya_existe(
                    connection=connection,
                    link_origen=link,
                    fuente_id=fuente_id,
                    codigo_externo=data.get("codigo_externo")
                )

                if publicacion_existente_id:
                    total_saltadas += 1
                    if update_existing_coordinates(connection, publicacion_existente_id, data):
                        print(f"[OK] Coordenadas agregadas a publicacion existente ID {publicacion_existente_id}: {data['coordenadas']}")
                    print(f"[SKIP] Ya existe en base de datos por link o código. ID {publicacion_existente_id}")
                    continue

                try:
                    publicacion_id = insert_publicacion(connection, data)
                except IntegrityError:
                    publicacion_existente_id = publicacion_ya_existe(
                        connection=connection,
                        link_origen=link,
                        fuente_id=fuente_id,
                        codigo_externo=data.get("codigo_externo")
                    )

                    if publicacion_existente_id:
                        total_saltadas += 1
                        if update_existing_coordinates(connection, publicacion_existente_id, data):
                            print(f"[OK] Coordenadas agregadas a publicacion existente ID {publicacion_existente_id}: {data['coordenadas']}")
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

                detect_duplicates_safely(connection, publicacion_id)

                print(f"[OK] Guardada publicación nueva ID {publicacion_id}")
                print(f"[OK] Código externo: {data['codigo_externo']}")
                print(f"[OK] Tipo: {data['tipo_inmueble']}")
                print(f"[OK] Dirección: {data['direccion']}")
                print(f"[OK] Barrio: {data['barrio']}")
                print(f"[OK] Precio: {data['precio']}")
                print(f"[OK] Área: {data['m2']} | Construida: {data['m2_construido']}")
                print(f"[OK] Habitaciones: {data['habitaciones']} | Baños: {data['banios']} | Parqueadero: {data['parqueadero']}")
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
    print(f"[RESUMEN] Omitidas sin precio: {total_sin_precio}")
    print(f"[RESUMEN] Omitidas fuera de Pasto: {total_fuera_de_pasto}")
    print(f"[RESUMEN] Errores: {total_errores}")
    audit.set_processing_counts(
        nuevas=total_nuevas,
        saltadas=total_saltadas,
        omitidas_sin_precio=total_sin_precio,
        omitidas_fuera_de_pasto=total_fuera_de_pasto,
        errores=total_errores,
    )
    audit.print_summary(len(publication_links))
    audit.save(len(publication_links))


if __name__ == "__main__":
    main()
