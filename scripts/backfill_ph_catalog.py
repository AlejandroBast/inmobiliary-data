"""Relaciona publicaciones ya guardadas con un nombre de PH del catalogo.

Usa exclusivamente catalog_match_in_text() (data/pasto_ph.tsv), NO detect_ph()
completo: detect_ph tambien cae a un extractor generico por regex ("Conjunto/
Edificio/Torre <lo que siga hasta una palabra de corte>") pensado para texto
recien scrapeado, y contra 3000+ descripciones libres ya guardadas ese
extractor capturaba basura ("torre ladera a una cuadra del patio taller
sitp..."). Este script solo debe escribir nombres que esten realmente en el
catalogo curado por el cliente.

Por defecto corre en modo dry-run (solo genera un reporte JSON en
logs/backfill_ph/). Con --apply escribe los cambios.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

# La consola de Windows usa cp1252 por defecto: descripcion trae emojis y
# caracteres que ese codec no sabe imprimir, y el script explota al final
# despues de haber hecho todo el trabajo. UTF-8 explicito lo evita.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from inmobiliary.detectors.ph import catalog_match_in_text


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "front" / ".env.local")
load_dotenv(ROOT / ".env", override=False)


def connection_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "db_inmobiliary_data"),
    }


def analyze(rows):
    changes = []
    for row in rows:
        # publicaciones no guarda el titulo del portal por separado: descripcion
        # y direccion son los unicos campos de texto libre que persisten.
        nuevo = catalog_match_in_text(row["descripcion"], row["direccion"])
        anterior = row["ph"]
        # Solo interesa cuando el catalogo aporta un nombre distinto al que ya
        # tenia la fila (evita pisar ediciones manuales con el mismo valor).
        if nuevo and nuevo != anterior:
            changes.append({"id": row["id"], "ph_anterior": anterior, "ph_nuevo": nuevo})
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica los cambios dentro de una transaccion.")
    args = parser.parse_args()

    connection = mysql.connector.connect(**connection_config())
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, descripcion, direccion, ph FROM publicaciones ORDER BY id")
    rows = cursor.fetchall()
    changes = analyze(rows)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if args.apply else "dry-run",
        "total": len(rows),
        "changes": changes,
    }
    reports_dir = ROOT / "logs" / "backfill_ph"
    reports_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"backfill_{'apply' if args.apply else 'dry_run'}_{suffix}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.apply and changes:
        try:
            connection.rollback()
            connection.start_transaction()
            cursor.executemany(
                "UPDATE publicaciones SET ph = %s WHERE id = %s",
                [(item["ph_nuevo"], item["id"]) for item in changes],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    cursor.close()
    connection.close()

    print(json.dumps({
        "mode": report["mode"],
        "total": len(rows),
        "changes": len(changes),
        "report": str(report_path),
        "proposed_changes": changes,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
