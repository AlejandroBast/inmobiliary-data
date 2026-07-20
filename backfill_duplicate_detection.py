"""Analiza publicaciones historicas de forma incremental y reanudable."""

import argparse
import os

import mysql.connector
from dotenv import load_dotenv

from db_config import get_db_config
from duplicate_detector import detect_duplicates_safely


load_dotenv()

BATCH_SIZE = int(os.getenv("DUPLICATE_BACKFILL_BATCH_SIZE", "100"))


def reset_automatic_results(connection):
    """Elimina solo resultados derivados; nunca publicaciones ni evidencias."""
    cursor = connection.cursor()
    cursor.execute("DELETE FROM inmuebles_detectados")
    cursor.execute("DELETE FROM coincidencias_publicaciones WHERE estado <> 'descartada'")
    connection.commit()
    cursor.close()


def pending_publication_ids(connection):
    cursor = connection.cursor()
    cursor.execute(
        """SELECT p.id
           FROM publicaciones p
           WHERE EXISTS (
               SELECT 1 FROM evidencias_publicacion e
               WHERE e.publicacion_id = p.id AND e.tipo = 'imagen'
           )
           ORDER BY p.id"""
    )
    ids = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return ids


def main():
    parser = argparse.ArgumentParser(description="Recalcula coincidencias de publicaciones")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="limpia resultados automaticos anteriores antes de recalcular",
    )
    args = parser.parse_args()
    connection = mysql.connector.connect(**get_db_config())
    try:
        if args.rebuild:
            reset_automatic_results(connection)
            print("[INFO] Resultados automaticos anteriores limpiados")
        publication_ids = pending_publication_ids(connection)
        print(f"[INFO] Publicaciones con imagenes por analizar: {len(publication_ids)}")
        for start in range(0, len(publication_ids), BATCH_SIZE):
            batch = publication_ids[start:start + BATCH_SIZE]
            for publication_id in batch:
                detect_duplicates_safely(connection, publication_id)
            print(f"[INFO] Procesadas {min(start + len(batch), len(publication_ids))}/{len(publication_ids)}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
