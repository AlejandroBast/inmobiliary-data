"""Aplica de forma idempotente las tablas de catalogos (barrios, tipos_inmueble)."""

from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

from db_config import get_db_config


load_dotenv()


def main():
    connection = mysql.connector.connect(**get_db_config())
    cursor = connection.cursor()
    try:
        migration = Path(__file__).with_name("migrations") / "003_catalogos_ubicacion_tipo.sql"
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
                 AND table_name IN ('barrios', 'tipos_inmueble')"""
        )
        print(f"[OK] Tablas de catalogos disponibles: {cursor.fetchone()[0]}/2")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
