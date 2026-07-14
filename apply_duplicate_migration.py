"""Aplica de forma idempotente las tablas del detector de duplicados."""

import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


load_dotenv()


def main():
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "boludo123"),
        database=os.getenv("DB_NAME", "db_inmobiliary_data"),
    )
    cursor = connection.cursor()
    try:
        migration = Path(__file__).with_name("migrations") / "001_duplicate_detection.sql"
        sql = migration.read_text(encoding="utf-8")
        statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
        for statement in statements:
            try:
                cursor.execute(statement)
            except Exception:
                print(f"[ERROR] Fallo la sentencia que comienza con: {statement[:80]}")
                cursor.execute("SHOW WARNINGS")
                for warning in cursor.fetchall():
                    print(f"[MYSQL] {warning}")
                raise

        cursor.execute(
            """SELECT COUNT(*) FROM information_schema.columns
               WHERE table_schema = DATABASE()
                 AND table_name = 'imagenes_hashes'
                 AND column_name = 'hash_contenido'"""
        )
        if cursor.fetchone()[0] == 0:
            exact_hash_migration = (
                Path(__file__).with_name("migrations") / "002_exact_image_hash.sql"
            )
            cursor.execute(exact_hash_migration.read_text(encoding="utf-8").strip().rstrip(";"))
        cursor.execute(
            """SELECT character_maximum_length, is_nullable, collation_name
               FROM information_schema.columns
               WHERE table_schema = DATABASE()
                 AND table_name = 'imagenes_hashes'
                 AND column_name = 'hash_contenido'"""
        )
        exact_hash_column = cursor.fetchone()
        if exact_hash_column != (64, "YES", "ascii_bin"):
            cursor.execute(
                """ALTER TABLE imagenes_hashes MODIFY COLUMN hash_contenido
                   CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL"""
            )
        connection.commit()
        cursor.execute(
            """SELECT COUNT(*) FROM information_schema.tables
               WHERE table_schema = DATABASE()
                 AND table_name IN (
                    'inmuebles_detectados', 'publicaciones_inmueble',
                    'imagenes_hashes', 'coincidencias_publicaciones'
                 )"""
        )
        print(f"[OK] Tablas del detector disponibles: {cursor.fetchone()[0]}/4")
        cursor.execute(
            """SELECT COUNT(*) FROM information_schema.columns
               WHERE table_schema = DATABASE()
                 AND table_name = 'imagenes_hashes'
                 AND column_name = 'hash_contenido'"""
        )
        print(f"[OK] Hash SHA-256 disponible: {'si' if cursor.fetchone()[0] else 'no'}")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
