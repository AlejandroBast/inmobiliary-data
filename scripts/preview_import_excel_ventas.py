"""Vista previa (solo lectura) de la importacion del Excel del cliente.

Lee la hoja "Ventas" del Excel, limpia cada columna con las mismas reglas que
se usarian para insertar, y genera un reporte en logs/. NO escribe nada en
MySQL ni modifica el Excel: es el paso previo para decidir las reglas de
limpieza antes de tocar la base de datos.

Uso:
    py -3 scripts/preview_import_excel_ventas.py "ruta/al/archivo.xlsx"
"""

import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inmobiliary.detectors.location import resolve_pasto_location, location_diagnostic  # noqa: E402
from inmobiliary.detectors.ph import detect_ph  # noqa: E402


def normalize_header(value):
    if not value:
        return ""
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


# Cada clave interna mapea a los posibles encabezados normalizados que puede
# traer el Excel (tolerante a tildes/mayusculas rotas por la exportacion).
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

# Columnas confirmadas como muertas/no usadas: no se leen ni se reportan.
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


def build_column_map(headers):
    normalized = [normalize_header(h) for h in headers]
    column_map = {}
    unmatched = []

    for index, header_norm in enumerate(normalized):
        if not header_norm:
            continue
        if header_norm in IGNORED_HEADERS:
            continue

        matched_key = None
        for key, aliases in HEADER_ALIASES.items():
            if header_norm in aliases:
                matched_key = key
                break

        if matched_key:
            column_map[matched_key] = index
        else:
            unmatched.append(headers[index])

    return column_map, unmatched


def as_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    return None


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
        return "Cliente (sin fuente identificada)"
    lowered = str(link).lower()
    for domain, nombre in KNOWN_PORTAL_DOMAINS:
        if domain in lowered:
            return nombre
    return "Cliente (sin fuente identificada)"


def clean_date(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    return None


def main():
    if len(sys.argv) < 2:
        print("Uso: py -3 scripts/preview_import_excel_ventas.py <ruta_excel>")
        sys.exit(1)

    path = Path(sys.argv[1])
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Ventas"]

    rows_iter = ws.iter_rows(values_only=True)
    headers = next(rows_iter)
    column_map, unmatched_headers = build_column_map(headers)

    print("[INFO] Columnas reconocidas:", sorted(column_map.keys()))
    if unmatched_headers:
        print("[WARN] Encabezados no reconocidos (se ignoran):", unmatched_headers)

    def get(row, key):
        index = column_map.get(key)
        if index is None or index >= len(row):
            return None
        value = row[index]
        return value if value not in (None, "") else None

    total = 0
    importables = []
    omitidos = {"sin_precio": 0, "sin_link": 0}
    contaminacion = {
        "estrato_texto": 0, "estrato_via_estrato_anuncio": 0,
        "m2_construido_es_dimension_lote": 0,
        "administracion_texto": 0,
        "parqueadero_no_numerico": 0,
        "pisos_no_numerico": 0, "habitaciones_no_numerico": 0, "banios_no_numerico": 0,
        "coordenadas_placeholder_o_invalida": 0,
    }
    fuentes_inferidas = {}
    barrios_sin_normalizar = []

    for row in rows_iter:
        if all(v in (None, "") for v in row):
            continue
        total += 1

        precio = as_number(get(row, "precio"))
        link = get(row, "link")

        if not precio or precio <= 0:
            omitidos["sin_precio"] += 1
            continue
        if not link:
            omitidos["sin_link"] += 1
            continue

        estrato = as_number(get(row, "estrato"))
        if get(row, "estrato") is not None and estrato is None:
            contaminacion["estrato_texto"] += 1
            estrato = as_number(get(row, "estrato_anuncio"))
            if estrato is not None:
                contaminacion["estrato_via_estrato_anuncio"] += 1

        m2_construido_raw = get(row, "m2_construido")
        m2_construido = as_number(m2_construido_raw)
        if m2_construido_raw is not None and m2_construido is None:
            if looks_like_lot_dimensions(m2_construido_raw):
                contaminacion["m2_construido_es_dimension_lote"] += 1

        administracion = as_number(get(row, "administracion"))
        if get(row, "administracion") is not None and administracion is None:
            contaminacion["administracion_texto"] += 1

        parqueadero = as_number(get(row, "parqueadero"))
        if get(row, "parqueadero") is not None and parqueadero is None:
            contaminacion["parqueadero_no_numerico"] += 1

        pisos = as_number(get(row, "pisos"))
        if get(row, "pisos") is not None and pisos is None:
            contaminacion["pisos_no_numerico"] += 1

        habitaciones = as_number(get(row, "habitaciones"))
        if get(row, "habitaciones") is not None and habitaciones is None:
            contaminacion["habitaciones_no_numerico"] += 1

        banios = as_number(get(row, "banios"))
        if get(row, "banios") is not None and banios is None:
            contaminacion["banios_no_numerico"] += 1

        coordenadas_raw = get(row, "coordenadas")
        coordenadas, latitud, longitud = clean_coordenadas(coordenadas_raw)
        if coordenadas_raw is not None and coordenadas is None:
            contaminacion["coordenadas_placeholder_o_invalida"] += 1

        barrio_raw = get(row, "barrio")
        titulo = None
        descripcion = get(row, "descripcion")
        ph_excel = get(row, "ph")
        tipo_inmueble = get(row, "tipo_inmueble")

        location_result = resolve_pasto_location(
            barrio_raw, title=titulo, description=descripcion, ph=ph_excel
        )
        if not location_result.accepted:
            barrios_sin_normalizar.append(barrio_raw)

        ph = ph_excel or detect_ph(descripcion)

        fuente = infer_fuente(link)
        fuentes_inferidas[fuente] = fuentes_inferidas.get(fuente, 0) + 1

        importables.append({
            "codigo_externo": get(row, "codigo"),
            "link_origen": link,
            "links_adicionales": {
                "link_2": get(row, "link2"),
                "link_3": get(row, "link3"),
                "concepto_excel": get(row, "concepto"),
                "avaluo_catastral_excel": get(row, "avaluo"),
                "fecha_excel": clean_date(get(row, "fecha")),
                "fecha_actualizacion_excel": clean_date(get(row, "fecha_actualizacion")),
                "fuente_importacion": "excel_cliente",
            },
            "coordenadas": coordenadas,
            "latitud": latitud,
            "longitud": longitud,
            "barrio": location_result.value if location_result.accepted else barrio_raw,
            "barrio_normalizado": location_result.accepted,
            "tipo_inmueble": str(tipo_inmueble).strip().title() if tipo_inmueble else None,
            "ph": ph,
            "estrato": int(estrato) if estrato is not None else None,
            "descripcion": descripcion,
            "notas": get(row, "observacion"),
            "precio": precio,
            "m2": as_number(get(row, "m2")),
            "m2_construido": m2_construido,
            "pisos": int(pisos) if pisos is not None else None,
            "habitaciones": int(habitaciones) if habitaciones is not None else None,
            "banios": int(banios) if banios is not None else None,
            "parqueadero": int(parqueadero) if parqueadero is not None else None,
            "administracion": administracion,
            "fuente_inferida": fuente,
        })

    report = {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "archivo": str(path),
        "hoja": "Ventas",
        "total_filas_con_datos": total,
        "importables": len(importables),
        "omitidos": omitidos,
        "contaminacion_por_columna": contaminacion,
        "fuentes_inferidas_por_link": fuentes_inferidas,
        "barrios_sin_normalizar_muestra": barrios_sin_normalizar[:30],
        "barrios_sin_normalizar_total": len(barrios_sin_normalizar),
        "encabezados_no_reconocidos": unmatched_headers,
        "muestra_filas_limpias": importables[:15],
    }

    logs_dir = ROOT / "logs" / "import_excel_preview"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_path = logs_dir / f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\n[OK] Total filas con datos: {total}")
    print(f"[OK] Importables (con precio y link validos): {len(importables)}")
    print(f"[OK] Omitidos sin precio: {omitidos['sin_precio']}")
    print(f"[OK] Omitidos sin link: {omitidos['sin_link']}")
    print("[OK] Contaminacion detectada por columna:")
    for key, value in contaminacion.items():
        print(f"     - {key}: {value}")
    print("[OK] Fuentes inferidas por dominio del link:")
    for fuente, count in sorted(fuentes_inferidas.items(), key=lambda item: -item[1]):
        print(f"     - {fuente}: {count}")
    print(f"[OK] Barrios que no calzan con el catalogo oficial: {len(barrios_sin_normalizar)}")
    print(f"[OK] Reporte completo guardado en: {out_path}")


if __name__ == "__main__":
    main()
