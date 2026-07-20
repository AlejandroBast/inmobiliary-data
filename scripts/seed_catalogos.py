"""Siembra los catalogos de barrios y tipos de inmueble sin afectar publicaciones.

Por defecto corre en modo dry-run (solo genera un reporte JSON en
logs/catalogos_seed/). Con --apply inserta las filas nuevas en los catalogos
y corrige el casing de publicaciones.barrio/tipo_inmueble para que coincida
con el texto canonico del catalogo (mismo valor normalizado, distinto casing).
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

from inmobiliary.detectors.location import load_catalog, normalize_text


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "front" / ".env.local")
load_dotenv(ROOT / ".env", override=False)

BARRIO_PREFIX_RE = re.compile(r"^(barrio|vereda|corregimiento|b|br|bo)\s+")
BASE_TIPOS = ["Apartamento", "Casa", "Local", "Oficina", "Lote", "Bodega", "Consultorio", "Finca"]


def normalize_barrio_key(value):
    text = normalize_text(value)
    if not text:
        return None
    text = BARRIO_PREFIX_RE.sub("", text)
    text = text.strip()
    return text or None


def normalize_tipo_key(value):
    return normalize_text(value) or None


def title_case(value):
    return " ".join(word.capitalize() for word in value.strip().split())


def connection_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "db_inmobiliary_data"),
    }


def build_barrio_seed(existing_barrio_values):
    catalog = {}
    urban, rural = load_catalog()
    for entry in list(urban.values()) + list(rural.values()):
        key = normalize_barrio_key(entry.canonical)
        if key:
            catalog.setdefault(key, entry.canonical)

    for raw in existing_barrio_values:
        key = normalize_barrio_key(raw)
        if key:
            catalog.setdefault(key, raw.strip())

    return catalog


def build_tipo_seed(existing_tipo_values):
    catalog = {}
    for name in BASE_TIPOS:
        key = normalize_tipo_key(name)
        if key:
            catalog.setdefault(key, name)

    for raw in existing_tipo_values:
        key = normalize_tipo_key(raw)
        if key:
            catalog.setdefault(key, title_case(raw))

    return catalog


def main():
    parser = argparse.ArgumentParser(description="Siembra catalogos de barrios y tipos de inmueble.")
    parser.add_argument("--apply", action="store_true", help="Escribe los cambios (por defecto es dry-run).")
    args = parser.parse_args()

    connection = mysql.connector.connect(**connection_config())
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT DISTINCT barrio FROM publicaciones WHERE barrio IS NOT NULL AND TRIM(barrio) <> ''"
    )
    existing_barrios = [row["barrio"] for row in cursor.fetchall()]

    cursor.execute(
        "SELECT DISTINCT tipo_inmueble FROM publicaciones WHERE tipo_inmueble IS NOT NULL AND TRIM(tipo_inmueble) <> ''"
    )
    existing_tipos = [row["tipo_inmueble"] for row in cursor.fetchall()]

    barrio_seed = build_barrio_seed(existing_barrios)
    tipo_seed = build_tipo_seed(existing_tipos)

    cursor.execute("SELECT nombre, nombre_normalizado FROM barrios")
    existing_barrio_rows = {row["nombre_normalizado"]: row["nombre"] for row in cursor.fetchall()}
    cursor.execute("SELECT nombre, nombre_normalizado FROM tipos_inmueble")
    existing_tipo_rows = {row["nombre_normalizado"]: row["nombre"] for row in cursor.fetchall()}

    new_barrios = {k: v for k, v in barrio_seed.items() if k not in existing_barrio_rows}
    new_tipos = {k: v for k, v in tipo_seed.items() if k not in existing_tipo_rows}

    barrio_canonical_by_key = {**existing_barrio_rows, **new_barrios}
    tipo_canonical_by_key = {**existing_tipo_rows, **new_tipos}

    cursor.execute("SELECT id, barrio FROM publicaciones WHERE barrio IS NOT NULL AND TRIM(barrio) <> ''")
    barrio_case_fixes = []
    for row in cursor.fetchall():
        key = normalize_barrio_key(row["barrio"])
        canon = barrio_canonical_by_key.get(key) if key else None
        if canon and canon != row["barrio"]:
            barrio_case_fixes.append({"id": row["id"], "anterior": row["barrio"], "nuevo": canon})

    cursor.execute(
        "SELECT id, tipo_inmueble FROM publicaciones WHERE tipo_inmueble IS NOT NULL AND TRIM(tipo_inmueble) <> ''"
    )
    tipo_case_fixes = []
    for row in cursor.fetchall():
        key = normalize_tipo_key(row["tipo_inmueble"])
        canon = tipo_canonical_by_key.get(key) if key else None
        if canon and canon != row["tipo_inmueble"]:
            tipo_case_fixes.append({"id": row["id"], "anterior": row["tipo_inmueble"], "nuevo": canon})

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if args.apply else "dry-run",
        "counts": {
            "new_barrios": len(new_barrios),
            "new_tipos": len(new_tipos),
            "barrio_case_fixes": len(barrio_case_fixes),
            "tipo_case_fixes": len(tipo_case_fixes),
        },
        "new_barrios": sorted(new_barrios.values(), key=str.lower),
        "new_tipos": sorted(new_tipos.values(), key=str.lower),
        "barrio_case_fixes": barrio_case_fixes,
        "tipo_case_fixes": tipo_case_fixes,
    }

    reports_dir = ROOT / "logs" / "catalogos_seed"
    reports_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"seed_{'apply' if args.apply else 'dry_run'}_{suffix}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.apply:
        try:
            connection.rollback()
            connection.start_transaction()
            if new_barrios:
                cursor.executemany(
                    "INSERT INTO barrios (nombre, nombre_normalizado) VALUES (%s, %s)",
                    [(v, k) for k, v in new_barrios.items()],
                )
            if new_tipos:
                cursor.executemany(
                    "INSERT INTO tipos_inmueble (nombre, nombre_normalizado) VALUES (%s, %s)",
                    [(v, k) for k, v in new_tipos.items()],
                )
            if barrio_case_fixes:
                cursor.executemany(
                    "UPDATE publicaciones SET barrio = %s WHERE id = %s",
                    [(f["nuevo"], f["id"]) for f in barrio_case_fixes],
                )
            if tipo_case_fixes:
                cursor.executemany(
                    "UPDATE publicaciones SET tipo_inmueble = %s WHERE id = %s",
                    [(f["nuevo"], f["id"]) for f in tipo_case_fixes],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    cursor.close()
    connection.close()

    print(json.dumps({
        "mode": report["mode"],
        "counts": report["counts"],
        "report": str(report_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
