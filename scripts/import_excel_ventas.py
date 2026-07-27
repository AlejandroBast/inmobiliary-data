"""Importa la hoja "Ventas" del Excel del cliente hacia `publicaciones`.

Por defecto corre en modo DRY-RUN: aplica todas las reglas de limpieza,
genera un reporte en logs/import_excel/, pero no escribe nada en MySQL.
Con --apply, inserta de verdad (una fila a la vez, saltando duplicados por
link_origen igual que hacen los scrapers).

No modifica el esquema: solo llena columnas que ya existen en `publicaciones`.
Lo que no tiene columna propia (link 2/3, concepto, avaluo catastral, fechas
del excel) va a `links_adicionales` (JSON), igual que ya hacen los scrapers
con datos de diagnostico.

Uso:
    py -3 scripts/import_excel_ventas.py "ruta/al/archivo.xlsx"            # dry-run
    py -3 scripts/import_excel_ventas.py "ruta/al/archivo.xlsx" --apply    # escribe
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import openpyxl
from mysql.connector import IntegrityError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inmobiliary.common import get_connection, get_or_create_fuente_id, publicacion_ya_existe  # noqa: E402
from inmobiliary.detectors.location import resolve_pasto_location  # noqa: E402
from inmobiliary.detectors.ph import detect_ph  # noqa: E402


def normalize_header(value):
    if not value:
        return ""
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


def normalize_plain(value):
    if not value:
        return ""
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text.lower().strip())


HEADER_ALIASES = {
    "coordenadas": ["localizacion coordenadas"],
    "tipo_inmueble": ["tipo de inmueble"],
    "concepto": ["concepto"],
    "fecha": ["fecha"],
    "precio": ["precio"],
    "barrio": ["barrio"],
    "ph": ["ph-o especif"],
    "estrato": ["estrato"],
    "estrato_anuncio": ["estrato del anuncio"],
    "m2": ["m2"],
    "m2_construido": ["m2 construidos"],
    "pisos": ["pisos"],
    "habitaciones": ["habitaciones"],
    "banios": ["bano", "banio"],
    "parqueadero": ["parqueadero"],
    "descripcion": ["descripcion"],
    "observacion": ["observacion (antes en esta columna decia valor gastos)", "observacion"],
    "administracion": ["administracion"],
    "avaluo": ["avaluo catastral"],
    "link": ["link"],
    "link2": ["link 2"],
    "link3": ["link 3"],
    "codigo": ["codigo"],
    "fecha_actualizacion": ["fecha actualizacion"],
}

IGNORED_HEADERS = {
    "unidad territorial", "area de actividad humana", "area morfologica",
    "ubicacion manzana", "ubicacion supermanzana", "acceso a la via",
    "metraje de frente por metraje de fondo", "material de estructuras",
    "fecha de construccion", "estado de conservacion", "uso de suelo",
    "nivel sobre o bajo la via", "pendiente", "antiguedad barrio",
    "1 a 5 estrellas", "fecha no disponible", "no", "precio m2 constru",
}

KNOWN_PORTAL_DOMAINS = [
    ("fincaraiz.com.co", "Fincaraiz"),
    ("metrocuadrado.com", "Metrocuadrado"),
    ("ciencuadras.com", "Ciencuadras"),
    ("facebook.com", "Facebook Marketplace"),
    ("amorelpasto.com", "Amorel"),
]

FUENTE_METADATA = {
    "Fincaraiz": ("https://www.fincaraiz.com.co", "portal"),
    "Metrocuadrado": ("https://www.metrocuadrado.com", "portal"),
    "Ciencuadras": ("https://www.ciencuadras.com", "portal"),
    "Facebook Marketplace": ("https://www.facebook.com/marketplace/", "marketplace"),
    "Amorel": ("https://amorelpasto.com", "clasificados"),
    "Cliente": (None, "manual"),
}

# Municipios vecinos que a veces aparecen literalmente en la columna "barrio"
# del Excel en vez de un barrio de Pasto. Coincide con lo que ya usan los
# scrapers (detectors/location.py OUTSIDE_PLACES + facebook.py OUT_OF_CITY),
# mas "puerres" que aparecio en este Excel y no estaba en ninguna lista.
OUTSIDE_MUNICIPIOS = {
    "bogota", "bello", "buesaco", "chachagui", "cundinamarca", "girardot",
    "imues", "medellin", "mocoa", "ricaurte", "sandona", "taminango",
    "ipiales", "tuquerres", "tumaco", "la union", "consaca", "yacuanquer",
    "tangua", "popayan", "pitalito", "puerres",
}

PH_BARRIO_PREFIX = re.compile(r"^\s*ph\s*[-:]\s*(.+)$", re.IGNORECASE)


def build_column_map(headers):
    normalized = [normalize_header(h) for h in headers]
    column_map = {}
    unmatched = []

    for index, header_norm in enumerate(normalized):
        if not header_norm or header_norm in IGNORED_HEADERS:
            continue
        matched_key = next((key for key, aliases in HEADER_ALIASES.items() if header_norm in aliases), None)
        if matched_key:
            column_map[matched_key] = index
        else:
            unmatched.append(headers[index])

    return column_map, unmatched


def as_number(value):
    return float(value) if isinstance(value, (int, float)) else None


def looks_like_lot_dimensions(value):
    return isinstance(value, str) and re.search(r"\d\s*[x*]\s*\d", value, re.IGNORECASE)


def clean_coordenadas(value):
    if not isinstance(value, str):
        return None, None, None
    match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*,\s*(-?\d+(?:[.,]\d+)?)", value)
    if not match:
        return None, None, None
    try:
        lat = float(match.group(1).replace(",", "."))
        lon = float(match.group(2).replace(",", "."))
    except ValueError:
        return None, None, None
    if -5 <= lat <= 15 and -82 <= lon <= -66:
        return f"{lat},{lon}", lat, lon
    return None, None, None


def infer_fuente(link):
    if not link:
        return "Cliente"
    lowered = str(link).lower()
    for domain, nombre in KNOWN_PORTAL_DOMAINS:
        if domain in lowered:
            return nombre
    return "Cliente"


def clean_date(value):
    return value.date().isoformat() if isinstance(value, datetime) else None


def split_ph_from_barrio(barrio_raw):
    """Si el cliente puso el nombre del conjunto directo en "barrio" con el
    prefijo "PH -" (ej. "PH - Torres de Mariluz"), ese es el nombre del PH,
    no un barrio real. Se extrae para el campo `ph`, igual que ya hace
    fincaraiz.py cuando la ubicacion de la ficha resulta ser un conjunto."""
    if not isinstance(barrio_raw, str):
        return None, barrio_raw
    match = PH_BARRIO_PREFIX.match(barrio_raw)
    if match:
        return match.group(1).strip().title(), None
    return None, barrio_raw


def build_row_data(row, column_map):
    def get(key):
        index = column_map.get(key)
        if index is None or index >= len(row):
            return None
        value = row[index]
        return value if value not in (None, "") else None

    result = {"skip_reason": None}

    precio = as_number(get("precio"))
    link = get("link")

    if not precio or precio <= 0:
        result["skip_reason"] = "sin_precio"
        return result
    if not link:
        result["skip_reason"] = "sin_link"
        return result

    barrio_raw = get("barrio")
    if normalize_plain(barrio_raw) in OUTSIDE_MUNICIPIOS:
        result["skip_reason"] = "fuera_de_pasto"
        return result

    ph_from_barrio, barrio_raw = split_ph_from_barrio(barrio_raw)

    estrato = as_number(get("estrato"))
    estrato_source = "estrato"
    if get("estrato") is not None and estrato is None:
        estrato = as_number(get("estrato_anuncio"))
        estrato_source = "estrato_del_anuncio" if estrato is not None else None

    m2_construido = as_number(get("m2_construido"))

    administracion = as_number(get("administracion"))
    parqueadero = as_number(get("parqueadero"))
    pisos = as_number(get("pisos"))
    habitaciones = as_number(get("habitaciones"))
    banios = as_number(get("banios"))
    coordenadas, latitud, longitud = clean_coordenadas(get("coordenadas"))

    descripcion = get("descripcion")
    ph_excel = get("ph")
    tipo_inmueble = get("tipo_inmueble")

    location_result = resolve_pasto_location(barrio_raw, description=descripcion, ph=ph_excel or ph_from_barrio)
    if location_result.outside_municipality:
        result["skip_reason"] = "fuera_de_pasto"
        return result

    barrio = location_result.value if location_result.accepted else barrio_raw
    ph = ph_from_barrio or ph_excel or detect_ph(descripcion)

    link2 = get("link2")
    link3 = get("link3")
    links_adicionales = {
        "link_2": link2,
        "link_3": link3,
        "concepto_excel": get("concepto"),
        "avaluo_catastral_excel": get("avaluo"),
        "fecha_excel": clean_date(get("fecha")),
        "fecha_actualizacion_excel": clean_date(get("fecha_actualizacion")),
        "estrato_fuente": estrato_source,
        "fuente_importacion": "excel_cliente_estudio_mercado",
    }

    result.update({
        "codigo_externo": str(get("codigo")) if get("codigo") is not None else None,
        "link_origen": str(link).strip(),
        "links_adicionales": json.dumps(links_adicionales, ensure_ascii=False, default=str),
        "coordenadas": coordenadas,
        "latitud": latitud,
        "longitud": longitud,
        "direccion": None,
        "ciudad": "Pasto",
        "barrio": barrio,
        "tipo_inmueble": str(tipo_inmueble).strip().title() if tipo_inmueble else None,
        "ph": ph,
        "estrato": int(estrato) if estrato is not None else None,
        "descripcion": descripcion,
        "precio": precio,
        "m2": as_number(get("m2")),
        "m2_construido": m2_construido,
        "antiguedad": None,
        "pisos": int(pisos) if pisos is not None else None,
        "habitaciones": int(habitaciones) if habitaciones is not None else None,
        "banios": int(banios) if banios is not None else None,
        "parqueadero": int(parqueadero) if parqueadero is not None else None,
        "administracion": administracion,
        "notas": get("observacion"),
        "fuente_nombre": infer_fuente(link),
    })
    return result


INSERT_SQL = """
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
"""


def main():
    parser = argparse.ArgumentParser(description="Importa la hoja Ventas del Excel del cliente.")
    parser.add_argument("excel_path", help="Ruta al archivo .xlsx")
    parser.add_argument("--apply", action="store_true", help="Escribe en MySQL (por defecto es dry-run).")
    args = parser.parse_args()

    path = Path(args.excel_path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Ventas"]

    rows_iter = ws.iter_rows(values_only=True)
    headers = next(rows_iter)
    column_map, unmatched_headers = build_column_map(headers)

    print(f"[INFO] Modo: {'APLICAR (escribe en MySQL)' if args.apply else 'DRY-RUN (solo reporte)'}")
    print("[INFO] Columnas reconocidas:", sorted(column_map.keys()))
    if unmatched_headers:
        print("[WARN] Encabezados no reconocidos (se ignoran):", unmatched_headers)

    connection = get_connection() if args.apply else None
    fuente_id_cache = {}

    def resolve_fuente_id(nombre):
        if nombre in fuente_id_cache:
            return fuente_id_cache[nombre]
        url_base, tipo_fuente = FUENTE_METADATA.get(nombre, (None, "manual"))
        descripcion = (
            "Publicaciones importadas desde el estudio de mercado (Excel) del cliente."
            if nombre == "Cliente"
            else f"Incluye registros importados desde el estudio de mercado (Excel) del cliente, atribuidos a {nombre} por el dominio del link."
        )
        fuente_id = get_or_create_fuente_id(connection, nombre, url_base, tipo_fuente, descripcion)
        fuente_id_cache[nombre] = fuente_id
        return fuente_id

    total = 0
    nuevas = 0
    duplicadas = 0
    errores = 0
    omitidos = {"sin_precio": 0, "sin_link": 0, "fuera_de_pasto": 0}
    fuentes_contadas = {}
    muestra = []
    errores_detalle = []

    for row in rows_iter:
        if all(v in (None, "") for v in row):
            continue
        total += 1

        data = build_row_data(row, column_map)
        if data["skip_reason"]:
            omitidos[data["skip_reason"]] += 1
            continue

        fuentes_contadas[data["fuente_nombre"]] = fuentes_contadas.get(data["fuente_nombre"], 0) + 1

        if not args.apply:
            if len(muestra) < 10:
                muestra.append({k: v for k, v in data.items() if k not in ("skip_reason",)})
            continue

        try:
            fuente_id = resolve_fuente_id(data["fuente_nombre"])
            existente_id = publicacion_ya_existe(
                connection, link_origen=data["link_origen"], fuente_id=fuente_id, codigo_externo=data["codigo_externo"]
            )
            if existente_id:
                duplicadas += 1
                continue

            insert_data = {**data, "fuente_id": fuente_id}
            cursor = connection.cursor()
            cursor.execute(INSERT_SQL, insert_data)
            connection.commit()
            cursor.close()
            nuevas += 1
        except IntegrityError:
            connection.rollback()
            duplicadas += 1
        except Exception as error:
            connection.rollback()
            errores += 1
            errores_detalle.append({"link": data.get("link_origen"), "error": str(error)})

    if connection:
        connection.close()

    report = {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "archivo": str(path),
        "modo": "apply" if args.apply else "dry_run",
        "total_filas_con_datos": total,
        "nuevas": nuevas,
        "duplicadas": duplicadas,
        "errores": errores,
        "errores_detalle": errores_detalle[:20],
        "omitidos": omitidos,
        "fuentes": fuentes_contadas,
        "muestra_filas": muestra,
    }

    logs_dir = ROOT / "logs" / "import_excel"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_path = logs_dir / f"import_{'apply' if args.apply else 'dry_run'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\n[OK] Total filas con datos: {total}")
    if args.apply:
        print(f"[OK] Nuevas insertadas: {nuevas}")
        print(f"[OK] Duplicadas (link/codigo ya existia): {duplicadas}")
        print(f"[OK] Errores: {errores}")
    else:
        print(f"[OK] Importables (pasarian el filtro): {total - sum(omitidos.values())}")
    print(f"[OK] Omitidas sin precio: {omitidos['sin_precio']}")
    print(f"[OK] Omitidas sin link: {omitidos['sin_link']}")
    print(f"[OK] Omitidas fuera de Pasto: {omitidos['fuera_de_pasto']}")
    print("[OK] Fuentes:")
    for fuente, count in sorted(fuentes_contadas.items(), key=lambda item: -item[1]):
        print(f"     - {fuente}: {count}")
    print(f"[OK] Reporte guardado en: {out_path}")


if __name__ == "__main__":
    main()
