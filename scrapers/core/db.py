from pathlib import Path

import mysql.connector

from scrapers.core.config import get_db_config
from scrapers.core.evidence import file_hash


PUBLICACION_COLUMNS = (
    "fuente_id",
    "codigo_externo",
    "link_origen",
    "links_adicionales",
    "coordenadas",
    "latitud",
    "longitud",
    "direccion",
    "ciudad",
    "barrio",
    "tipo_inmueble",
    "ph",
    "estrato",
    "descripcion",
    "precio",
    "m2",
    "m2_construido",
    "antiguedad",
    "pisos",
    "habitaciones",
    "banios",
    "parqueadero",
    "administracion",
    "notas",
)


def get_connection(db_config=None):
    return mysql.connector.connect(**(db_config or get_db_config()))


def get_or_create_fuente_id(connection, nombre, url_base, tipo_fuente, descripcion):
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO fuentes_inmobiliarias
        (nombre, url_base, tipo_fuente, activa, descripcion)
        VALUES (%s, %s, %s, TRUE, %s)
        ON DUPLICATE KEY UPDATE
            id = LAST_INSERT_ID(id),
            activa = TRUE,
            url_base = VALUES(url_base),
            descripcion = VALUES(descripcion)
        """,
        (nombre, url_base, tipo_fuente, descripcion),
    )
    connection.commit()
    fuente_id = cursor.lastrowid
    cursor.close()
    return fuente_id


def publicacion_ya_existe(connection, link_origen=None, fuente_id=None, codigo_externo=None):
    cursor = connection.cursor()

    if codigo_externo and fuente_id:
        cursor.execute(
            """
            SELECT id
            FROM publicaciones
            WHERE link_origen = %s
               OR (fuente_id = %s AND codigo_externo = %s)
            LIMIT 1
            """,
            (link_origen, fuente_id, codigo_externo),
        )
    else:
        cursor.execute(
            """
            SELECT id
            FROM publicaciones
            WHERE link_origen = %s
            LIMIT 1
            """,
            (link_origen,),
        )

    result = cursor.fetchone()
    cursor.close()
    return result[0] if result else None


def insert_publicacion(connection, data):
    columns_sql = ", ".join(PUBLICACION_COLUMNS)
    placeholders_sql = ", ".join(f"%({column})s" for column in PUBLICACION_COLUMNS)

    cursor = connection.cursor()
    cursor.execute(
        f"""
        INSERT INTO publicaciones ({columns_sql})
        VALUES ({placeholders_sql})
        """,
        data,
    )
    connection.commit()
    publicacion_id = cursor.lastrowid
    cursor.close()
    return publicacion_id


def insert_evidencia(connection, publicacion_id, tipo, ruta_archivo, url_original=None):
    ruta_archivo = str(ruta_archivo) if ruta_archivo else None
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM evidencias_publicacion
        WHERE publicacion_id = %s
          AND tipo = %s
          AND ruta_archivo = %s
        LIMIT 1
        """,
        (publicacion_id, tipo, ruta_archivo),
    )

    if cursor.fetchone():
        cursor.close()
        return

    hash_archivo = file_hash(ruta_archivo) if ruta_archivo and Path(ruta_archivo).exists() else None

    cursor.execute(
        """
        INSERT INTO evidencias_publicacion
        (publicacion_id, tipo, ruta_archivo, url_original, hash_archivo)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (publicacion_id, tipo, ruta_archivo, url_original, hash_archivo),
    )
    connection.commit()
    cursor.close()


def update_existing_coordinates(connection, publicacion_id, data):
    if not data.get("coordenadas") and not (data.get("latitud") and data.get("longitud")):
        return False

    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE publicaciones
        SET
            coordenadas = COALESCE(NULLIF(coordenadas, ''), %s),
            latitud = COALESCE(latitud, %s),
            longitud = COALESCE(longitud, %s)
        WHERE id = %s
          AND (
              coordenadas IS NULL OR TRIM(coordenadas) = ''
              OR latitud IS NULL
              OR longitud IS NULL
          )
        """,
        (
            data.get("coordenadas"),
            data.get("latitud"),
            data.get("longitud"),
            publicacion_id,
        ),
    )
    connection.commit()
    updated = cursor.rowcount > 0
    cursor.close()
    return updated
