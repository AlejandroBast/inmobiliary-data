import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

from location_normalizer import location_diagnostic, normalize_text, resolve_pasto_location


ROOT = Path(__file__).resolve().parent
AUDITED_SAFE_IDS = {
    5, 13, 20, 23, 29, 35, 38, 39, 53, 57, 70, 76, 82, 86, 94, 103, 106,
    135, 140, 146, 154, 163, 167, 168, 177, 179, 183, 185, 193, 195, 198,
    211, 226, 229, 232, 235, 239, 240, 265, 278, 280, 281, 309, 320,
}
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
    review_only = []
    outside = []
    unresolved = []
    for row in rows:
        result = resolve_pasto_location(
            row["barrio"],
            description=row["descripcion"],
            address=row["direccion"],
            city=row["ciudad"],
            ph=row["ph"],
        )
        item = {
            "id": row["id"],
            "barrio_anterior": row["barrio"],
            "diagnostico": location_diagnostic(result),
        }
        if result.outside_municipality:
            outside.append(item)
        elif not result.accepted:
            unresolved.append(item)
        elif normalize_text(row["barrio"]) != normalize_text(result.value):
            proposal = {**item, "barrio_nuevo": result.value, "confianza": result.confidence}
            if row["id"] in AUDITED_SAFE_IDS:
                changes.append(proposal)
            else:
                review_only.append(proposal)
    return changes, review_only, outside, unresolved


def main():
    parser = argparse.ArgumentParser(description="Normaliza barrios existentes sin borrar publicaciones.")
    parser.add_argument("--apply", action="store_true", help="Aplica los cambios dentro de una transaccion.")
    args = parser.parse_args()

    connection = mysql.connector.connect(**connection_config())
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, barrio, ciudad, direccion, ph, descripcion FROM publicaciones ORDER BY id")
    rows = cursor.fetchall()
    changes, review_only, outside, unresolved = analyze(rows)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if args.apply else "dry-run",
        "total": len(rows),
        "changes": changes,
        "review_only_unchanged": review_only,
        "outside_pasto_unchanged": outside,
        "unresolved_unchanged": unresolved,
    }
    reports_dir = ROOT / "logs" / "location_normalization"
    reports_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"backfill_{'apply' if args.apply else 'dry_run'}_{suffix}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.apply and changes:
        try:
            connection.rollback()
            connection.start_transaction()
            cursor.executemany(
                "UPDATE publicaciones SET barrio = %s WHERE id = %s",
                [(item["barrio_nuevo"], item["id"]) for item in changes],
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
        "outside_unchanged": len(outside),
        "unresolved_unchanged": len(unresolved),
        "review_only_unchanged": len(review_only),
        "report": str(report_path),
        "proposed_changes": changes,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
