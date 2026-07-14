"""Analiza publicaciones historicas de forma incremental y reanudable."""

import os

import mysql.connector
from dotenv import load_dotenv

from duplicate_detector import detect_duplicates_safely


load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "boludo123"),
    "database": os.getenv("DB_NAME", "db_inmobiliary_data"),
}
BATCH_SIZE = int(os.getenv("DUPLICATE_BACKFILL_BATCH_SIZE", "100"))


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
    connection = mysql.connector.connect(**DB_CONFIG)
    try:
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

