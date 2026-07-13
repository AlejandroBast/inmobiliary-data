import os
import re
import json
import time
import html as html_module
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from mysql.connector import IntegrityError
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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
    save_screenshot as core_save_screenshot,
    download_images_parallel as core_download_images_parallel,
)
from scrapers.core.stats import print_scraper_summary, skip_bucket
from scrapers.core.normalizers import clean_text

SEARCH_URL = os.getenv(
    "METROCUADRADO_SEARCH_URL",
    "https://www.metrocuadrado.com/casalote-edificio-de-oficinas-edificio-de-apartamentos-apartamento-apartaestudio-casa-local-bodega-lote-finca-consultorio-oficina/venta/pasto/?search=form",
)
BASE_URL = "https://www.metrocuadrado.com"
DB_CONFIG = get_db_config()
EVIDENCE_PREFIX = "metrocuadrado"
get_connection = partial(core_get_connection, db_config=DB_CONFIG)
get_or_create_fuente_id = partial(
    core_get_or_create_fuente_id,
    nombre="Metrocuadrado",
    url_base=BASE_URL,
    tipo_fuente="portal",
    descripcion="Scraper de inmuebles en venta en Pasto desde Metrocuadrado.",
)
save_html = partial(core_save_html, prefix=EVIDENCE_PREFIX)
save_screenshot = partial(core_save_screenshot, prefix=EVIDENCE_PREFIX)

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
PUBLICATION_URL = os.getenv("PUBLICATION_URL")
# Metrocuadrado no debe heredar el MAX_PUBLICATIONS global usado para pruebas
# cortas de otros scrapers. Cero significa procesar todos los enlaces hallados.
MAX_PUBLICATIONS = int(os.getenv("METROCUADRADO_MAX_PUBLICATIONS", "0"))
LIST_SCROLLS = int(os.getenv("METROCUADRADO_LIST_SCROLLS", "0"))
SCROLL_STALL_LIMIT = int(os.getenv("METROCUADRADO_STALL_SCROLLS", "3"))
SEARCH_LOAD_WAIT_MS = int(os.getenv("SEARCH_LOAD_WAIT_MS", "3000"))
DETAIL_LOAD_WAIT_MS = int(os.getenv("DETAIL_LOAD_WAIT_MS", "1800"))
SCROLL_WAIT_MS = int(os.getenv("SCROLL_WAIT_MS", "1200"))
REQUEST_PAUSE_SECONDS = float(os.getenv("REQUEST_PAUSE_SECONDS", "0.5"))

DOWNLOAD_IMAGES = os.getenv("DOWNLOAD_IMAGES", "true").lower() == "true"
IMAGE_DOWNLOAD_WORKERS = int(os.getenv("IMAGE_DOWNLOAD_WORKERS", "6"))
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "12"))

EVIDENCE_DIR = Path("evidencias")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

TIPOS_INMUEBLE = [
    "Apartamento",
    "Casa lote",
    "Casa",
    "Lote",
    "Bodega",
    "Local Comercial",
    "Local",
    "Oficina",
    "Consultorio",
    "Finca",
    "Edificio de Oficinas",
    "Edificio",
]

def only_digits(value):
    if not value:
        return None

    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None

def extract_total_results(text):
    if not text:
        return None

    patterns = [
        r"([\d\.,]+)\s*[-\u2013]\s*([\d\.,]+)\s+de\s+([\d\.,]+)\s+resultados",
        r"de\s+([\d\.,]+)\s+resultados",
        r"([\d\.,]+)\s+resultados",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return only_digits(match.group(match.lastindex or 1))

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

def parse_decimal(value):
    if value is None:
        return None

    match = re.search(r"(\d+(?:[\.,]\d+)*)", str(value))
    if not match:
        return None

    number = match.group(1)

    if "," in number and "." in number:
        number = number.replace(".", "").replace(",", ".")
    elif "," in number:
        number = number.replace(",", ".")
    elif "." in number:
        parts = number.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 2:
            number = "".join(parts)

    try:
        return float(number)
    except ValueError:
        return None

def parse_int(value):
    if value is None:
        return None

    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None

def source_text(html):
    text = html_module.unescape(html or "")
    return text.replace('\\"', '"').replace("\\/", "/")

def regex_value(source, *patterns):
    for pattern in patterns:
        match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(match.group(1))

    return None

def regex_number(source, *patterns):
    value = regex_value(source, *patterns)
    return parse_decimal(value)

def decode_json_text(value):
    if not value:
        return None

    try:
        return clean_text(json.loads(f'"{value}"'))
    except Exception:
        return clean_text(value.replace("\\n", " ").replace('\\"', '"'))

def extract_codigo(url, source):
    return (
        regex_value(source, r'"propertyId"\s*:\s*"([^"]+)"')
        or regex_value(url, r"/([^/]*M\d+)(?:\?|#|$)")
        or regex_value(url, r"/([^/]+)$")
    )

def extract_title(source, text):
    return (
        regex_value(source, r'"title"\s*:\s*"([^"]+)"')
        or regex_value(text, r"([A-Za-zÁÉÍÓÚÑáéíóúñ ]+ en Venta,[^\n\r]+)")
    )

def extract_tipo(title, source):
    property_type = regex_value(source, r'"propertyType"\s*:\s*\{[^{}]*"nombre"\s*:\s*"([^"]+)"')
    if property_type:
        return property_type

    title = title or ""
    for tipo in TIPOS_INMUEBLE:
        if re.search(rf"\b{re.escape(tipo)}\b", title, re.IGNORECASE):
            return tipo

    return None

def extract_barrio(source, title):
    barrio = (
        regex_value(source, r'"commonNeighborhood"\s*:\s*"([^"]+)"')
        or regex_value(source, r'"neighborhood"\s*:\s*"([^"]+)"')
    )

    if barrio and barrio.upper() not in {"NA", "N/A", "OTROS"}:
        return barrio.title()

    match = re.search(r"en Venta,\s*([^,]+),\s*Pasto", title or "", re.IGNORECASE)
    if match:
        barrio = clean_text(match.group(1))
        return barrio.title() if barrio and barrio.upper() not in {"NA", "N/A"} else None

    return None

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

    if latitud is not None and longitud is not None and -5 <= latitud <= 15 and -82 <= longitud <= -66:
        return f"{latitud},{longitud}", latitud, longitud

    return None, None, None

def extract_coordinates(source):
    match = re.search(
        r'"coordinates"\s*:\s*\{\s*"lon"\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*"lat"\s*:\s*(-?\d+(?:\.\d+)?)',
        source,
        re.IGNORECASE,
    )
    if match:
        return coordinate_result(match.group(2), match.group(1))

    match = re.search(
        r'"localizacion"\s*:\s*\{\s*"lon"\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*"lat"\s*:\s*(-?\d+(?:\.\d+)?)',
        source,
        re.IGNORECASE,
    )
    if match:
        return coordinate_result(match.group(2), match.group(1))

    return None, None, None

def extract_image_urls(source):
    urls = []

    for match in re.finditer(r'"image(?:Mobile)?"\s*:\s*"([^"]+)"', source, re.IGNORECASE):
        urls.append(match.group(1))

    for match in re.finditer(r'https://multimedia\.metrocuadrado\.com/[^"\'\s<>]+', source, re.IGNORECASE):
        urls.append(match.group(0))

    cleaned = []
    seen = set()

    for url in urls:
        url = html_module.unescape(url).replace("\\/", "/").split("?")[0]
        lower = url.lower()

        if "multimedia.metrocuadrado.com" not in lower:
            continue
        if not re.search(r"\.(jpg|jpeg|png|webp)$", lower):
            continue

        identity = re.sub(r"_[phx]\.(jpg|jpeg|png|webp)$", "", lower)
        if identity in seen:
            continue

        seen.add(identity)
        cleaned.append(url)

    return cleaned

def save_existing_evidence(connection, html, image_urls, data, publicacion_id, link):
    codigo_archivo = data.get("codigo_externo") or f"publicacion_{publicacion_id}"
    html_path = save_html(html, codigo_archivo, publicacion_id)
    insert_evidencia(connection, publicacion_id, "html", html_path, link)
    print(f"[OK] HTML actualizado para publicacion existente ID {publicacion_id}")

    print(f"[INFO] Fotos detectadas para publicacion existente: {len(image_urls)}")
    downloaded_images = download_images_parallel(
        image_urls if DOWNLOAD_IMAGES else [],
        codigo_archivo,
        publicacion_id,
    )
    for _, image_url, image_path in downloaded_images:
        insert_evidencia(connection, publicacion_id, "imagen", image_path, image_url)

    if DOWNLOAD_IMAGES and image_urls and not downloaded_images:
        print(f"[WARN] No se pudo guardar ninguna foto para publicacion existente ID {publicacion_id}")

def download_image(image_url, codigo_archivo, index, publicacion_id):
    _, img_dir, _ = get_publication_evidence_dirs(publicacion_id)

    try:
        response = requests.get(
            image_url,
            timeout=IMAGE_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        response.raise_for_status()

        extension = Path(urlparse(image_url).path).suffix or ".jpg"
        filename = f"metrocuadrado_{sanitize_filename(codigo_archivo)}_{index}{extension}"
        path = img_dir / filename

        with open(path, "wb") as file:
            file.write(response.content)

        return path
    except Exception as error:
        print(f"[WARN] No se pudo descargar imagen: {image_url} | {error}")
        return None

download_images_parallel = partial(
    core_download_images_parallel,
    download_image_func=download_image,
    image_download_workers=IMAGE_DOWNLOAD_WORKERS,
    label="fotos",
)

def extract_listing_links_from_html(html):
    """Recupera tarjetas embebidas aunque el navegador no cree todos los <a>."""
    source = html_module.unescape(html or "")
    pattern = re.compile(
        r"(?:https?://(?:www\.)?metrocuadrado\.com)?"
        r"(/inmueble/venta-[^\"'< >?]+/\d+-M\d+)",
        re.IGNORECASE,
    )
    links = []
    for match in pattern.finditer(source):
        path = match.group(1)
        if "pasto" not in path.lower():
            continue
        link = urljoin(BASE_URL, path).rstrip("/")
        if link not in links:
            links.append(link)
    return links

def collect_publication_links(page):
    audit = ScraperAudit("Metrocuadrado", PUBLICATION_URL or SEARCH_URL)
    if PUBLICATION_URL:
        audit.set_listing_summary(
            total_reported=1,
            pages_expected=1,
            pages_planned=1,
            page_size=1,
        )
        audit.record_page("link_directo", url=PUBLICATION_URL, links_count=1, new_links_count=1)
        return [PUBLICATION_URL], audit

    print(f"[INFO] Abriendo listado: {SEARCH_URL}")
    try:
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception as error:
        reason = f"No se pudo abrir el listado: {error}"
        print(f"[ERROR] {reason}")
        audit.record_page(1, url=SEARCH_URL, status="error", reason=reason)
        return [], audit

    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(SEARCH_LOAD_WAIT_MS)
    try:
        body_text = page.locator("body").inner_text(timeout=15000)
    except Exception:
        body_text = ""

    total_results = extract_total_results(body_text)
    result_window = extract_result_window(body_text)
    page_size = None
    if result_window:
        start, end, window_total = result_window
        total_results = total_results or window_total
        page_size = max(end - start + 1, 1)

    audit.set_listing_summary(
        total_reported=total_results,
        pages_expected=None,
        pages_planned=LIST_SCROLLS if LIST_SCROLLS > 0 else None,
        page_size=page_size,
    )
    print(f"[INFO] Total resultados detectados: {total_results}")
    print(f"[INFO] Resultados por pagina detectados: {page_size}")
    print(
        f"[INFO] METROCUADRADO_LIST_SCROLLS: "
        f"{LIST_SCROLLS if LIST_SCROLLS > 0 else 'sin limite'}"
    )
    print(f"[INFO] Scrolls sin links nuevos para detener: {SCROLL_STALL_LIMIT}")

    links = extract_listing_links_from_html(page.content())
    print(f"[INFO] Links embebidos recuperados del HTML: {len(links)}")
    stalled_scrolls = 0

    scroll_index = 0
    reached_configured_limit = False
    while LIST_SCROLLS == 0 or scroll_index < LIST_SCROLLS:
        scroll_index += 1
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(SCROLL_WAIT_MS)

        current_links = page.eval_on_selector_all(
            "a[href]",
            """
            anchors => Array.from(new Set(
                anchors
                    .map(a => a.href)
                    .filter(Boolean)
                    .map(href => href.split('?')[0].split('#')[0])
            )).filter(href => {
                try {
                    const url = new URL(href);
                    return url.hostname.includes('metrocuadrado.com')
                        && url.pathname.includes('/inmueble/venta-')
                        && /M\\d+/i.test(url.pathname)
                        && url.pathname.toLowerCase().includes('pasto');
                } catch (error) {
                    return false;
                }
            })
            """,
        )

        new_links = 0
        duplicate_links = 0
        for link in current_links:
            if link not in links:
                links.append(link)
                new_links += 1
            else:
                duplicate_links += 1

        audit.record_scroll(
            scroll_index,
            links_count=len(current_links),
            new_links_count=new_links,
            duplicate_links_count=duplicate_links,
        )

        scroll_progress = f"{scroll_index}/{LIST_SCROLLS}" if LIST_SCROLLS > 0 else str(scroll_index)
        print(
            f"[INFO] Scroll {scroll_progress}: "
            f"{len(current_links)} visibles, {new_links} nuevos, {duplicate_links} repetidos, "
            f"{len(links)} acumulados"
        )

        if new_links == 0:
            stalled_scrolls += 1
        else:
            stalled_scrolls = 0

        if stalled_scrolls >= SCROLL_STALL_LIMIT:
            message = (
                f"Scroll detenido porque hubo {stalled_scrolls} scroll(s) seguidos "
                "sin links nuevos."
            )
            print(f"[INFO] {message}")
            audit.add_note(message)
            break

        reached_configured_limit = LIST_SCROLLS > 0 and scroll_index >= LIST_SCROLLS

    if reached_configured_limit and stalled_scrolls < SCROLL_STALL_LIMIT:
        audit.add_note(
            f"Se alcanzo METROCUADRADO_LIST_SCROLLS={LIST_SCROLLS}; si faltan anuncios, "
            "ese limite de seguridad puede haber detenido el recorrido."
        )

    if MAX_PUBLICATIONS > 0:
        if len(links) > MAX_PUBLICATIONS:
            audit.limit_reason = (
                f"Se encontraron {len(links)} links, pero MAX_PUBLICATIONS={MAX_PUBLICATIONS} "
                "recorto la lista procesada."
            )
        links = links[:MAX_PUBLICATIONS]

    audit.pages_planned = len(audit.page_results)

    return links, audit

def extract_publication_data(page, url, fuente_id):
    print(f"[INFO] Extrayendo publicacion: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(DETAIL_LOAD_WAIT_MS)

    html = page.content()
    text = page.locator("body").inner_text(timeout=15000)
    source = source_text(html)

    codigo_externo = extract_codigo(url, source)
    title = extract_title(source, text)
    precio = parse_int(regex_value(source, r'"salePrice"\s*:\s*(\d+)')) or only_digits(
        regex_value(text, r"\$\s*([\d\.]+)")
    )

    if not precio:
        print(f"[WARN] Omitida sin precio: {url}")
        return None, html, []

    tipo_inmueble = extract_tipo(title, source)
    barrio = extract_barrio(source, title)
    ciudad = regex_value(source, r'"city"\s*:\s*\{[^{}]*"nombre"\s*:\s*"([^"]+)"') or "Pasto"
    direccion = clean_text(", ".join(value for value in [barrio, ciudad, "Nariño"] if value))
    coordenadas, latitud, longitud = extract_coordinates(source)

    descripcion = regex_value(source, r'"comment"\s*:\s*"((?:\\.|[^"])*)"')
    descripcion = decode_json_text(descripcion)

    m2 = regex_number(source, r'"area"\s*:\s*"?(\d+(?:[\.,]\d+)?)"?')
    m2_construido = regex_number(source, r'"areac"\s*:\s*"?(\d+(?:[\.,]\d+)?)"?')
    habitaciones = parse_int(regex_value(source, r'"rooms"\s*:\s*"?(\d+)"?'))
    banios = parse_int(regex_value(source, r'"bathrooms"\s*:\s*"?(\d+)"?'))
    parqueadero = parse_int(regex_value(source, r'"garages"\s*:\s*"?(\d+)"?'))
    estrato = parse_int(regex_value(source, r'"estrato"\s*:\s*"?(\d+)"?'))
    antiguedad = regex_value(text, r"Antig[üu]edad:\s*([^\n\r]+)")
    pisos = parse_int(regex_value(text, r"N[uú]mero de piso\s+(\d+)"))

    image_urls = extract_image_urls(source)

    data = {
        "fuente_id": fuente_id,
        "codigo_externo": codigo_externo,
        "link_origen": url,
        "links_adicionales": None,
        "coordenadas": coordenadas,
        "latitud": latitud,
        "longitud": longitud,
        "direccion": direccion,
        "ciudad": ciudad,
        "barrio": barrio,
        "tipo_inmueble": tipo_inmueble,
        "ph": None,
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
        "administracion": None,
        "notas": None,
    }

    return data, html, image_urls

def main():
    print("[INFO] Iniciando scraper Metrocuadrado Pasto")
    print("[INFO] Fuente revisada: Metrocuadrado")
    connection = get_connection()
    fuente_id = get_or_create_fuente_id(connection)

    total_nuevas = 0
    total_saltadas = 0
    total_omitidas = 0
    total_sin_precio = 0
    total_no_venta = 0
    total_sin_barrio = 0
    total_errores = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        publication_links, audit = collect_publication_links(page)

        print(f"[INFO] Total links Metrocuadrado: {len(publication_links)}")

        for index, link in enumerate(publication_links, start=1):
            print(f"\n[INFO] Procesando {index}/{len(publication_links)}")

            try:
                data, html, image_urls = extract_publication_data(page, link, fuente_id)

                if not data:
                    total_omitidas += 1
                    total_sin_precio += 1
                    audit.record_omission("sin_datos_extraidos_o_sin_precio", link)
                    continue

                publicacion_existente_id = publicacion_ya_existe(
                    connection,
                    link_origen=link,
                    fuente_id=fuente_id,
                    codigo_externo=data.get("codigo_externo"),
                )

                if publicacion_existente_id:
                    total_saltadas += 1
                    save_existing_evidence(
                        connection,
                        html,
                        image_urls,
                        data,
                        publicacion_existente_id,
                        link,
                    )
                    print(f"[SKIP] Ya existe en base de datos. ID {publicacion_existente_id}")
                    continue

                try:
                    publicacion_id = insert_publicacion(connection, data)
                except IntegrityError as error:
                    connection.rollback()
                    publicacion_existente_id = publicacion_ya_existe(
                        connection,
                        link_origen=link,
                        fuente_id=fuente_id,
                        codigo_externo=data.get("codigo_externo"),
                    )

                    if publicacion_existente_id:
                        total_saltadas += 1
                        save_existing_evidence(
                            connection,
                            html,
                            image_urls,
                            data,
                            publicacion_existente_id,
                            link,
                        )
                        print(f"[SKIP] Ya existia al momento de insertar. ID {publicacion_existente_id}")
                        continue

                    total_errores += 1
                    print(f"[ERROR] No se pudo insertar {data.get('codigo_externo')}: {error}")
                    continue

                total_nuevas += 1
                codigo_archivo = data["codigo_externo"] or f"publicacion_{publicacion_id}"

                html_path = save_html(html, codigo_archivo, publicacion_id)
                insert_evidencia(connection, publicacion_id, "html", html_path, link)

                screenshot_path = save_screenshot(page, codigo_archivo, publicacion_id)
                if screenshot_path:
                    insert_evidencia(connection, publicacion_id, "screenshot", screenshot_path, link)

                print(f"[INFO] Fotos detectadas: {len(image_urls)}")
                downloaded_images = download_images_parallel(image_urls if DOWNLOAD_IMAGES else [], codigo_archivo, publicacion_id)
                for _, image_url, image_path in downloaded_images:
                    insert_evidencia(connection, publicacion_id, "imagen", image_path, image_url)

                print(f"[OK] Guardada publicacion nueva ID {publicacion_id}")
                print(f"[OK] Codigo externo: {data['codigo_externo']}")
                print(f"[OK] Tipo: {data['tipo_inmueble']} | Barrio: {data['barrio']}")
                print(f"[OK] Precio: {data['precio']} | Area: {data['m2']} | Construida: {data['m2_construido']}")
                print(f"[OK] Coordenadas: {data['coordenadas']}")

                if REQUEST_PAUSE_SECONDS > 0:
                    time.sleep(REQUEST_PAUSE_SECONDS)

            except Exception as error:
                total_errores += 1
                audit.record_error(link, error)
                print(f"[ERROR] Fallo publicacion {link}: {error}")

        browser.close()

    connection.close()

    print("\n[OK] Scraping Metrocuadrado finalizado.")
    print_scraper_summary(
        fuente="Metrocuadrado",
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
