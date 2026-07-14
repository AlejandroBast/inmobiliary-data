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
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
