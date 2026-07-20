"""Utilidades compartidas por los scrapers.

Cada scraper tenia su propia copia de estas funciones. Las copias derivaron
entre si, y esa deriva escondia errores: tres scrapers no desescapaban las
entidades HTML del texto, y uno no guardaba el hash de las evidencias. Aca
queda una sola version de cada una, la correcta.

Los extractores de HTML NO van aca: esos si son especificos de cada portal.
"""

import hashlib
import html as html_module
import re
import time
from pathlib import Path

try:
    import mysql.connector
except ImportError:
    mysql = None

from db_config import get_db_config


# ==========================================================
# TEXTO
# ==========================================================

def clean_text(value):
    """Normaliza espacios y desescapa entidades HTML."""
    if value is None:
        return None

    value = html_module.unescape(str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value if value else None


def get_lines(text):
    if not text:
        return []

    return [line.strip() for line in str(text).splitlines() if line.strip()]


def only_digits(value):
    if not value:
        return None

    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def parse_int(value):
    if value is None:
        return None

    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def parse_decimal(value):
    """Convierte un numero en formato colombiano a float.

    El punto puede ser separador de miles y la coma decimal:
        100 m2     -> 100.0
        118.65 m2  -> 118.65
        1.104 m2   -> 1104.0    (mil ciento cuatro, no uno coma uno)
        1.234,56   -> 1234.56

    Ciencuadras usaba una version que solo cambiaba coma por punto, y con eso
    un lote de 1.104 m2 quedaba guardado como 1.1 m2.
    """
    if value is None:
        return None

    match = re.search(r"(\d+(?:[\.,]\d+)*)", str(value))

    if not match:
        return None

    number = match.group(1)

    if "," in number and "." in number:
        number = number.replace(".", "").replace(",", ".")
    elif "," in number:
        number = number.replace(",", ".")
    elif "." in number:
        parts = number.split(".")
        # 1.104 son mil ciento cuatro; 118.65 son ciento dieciocho con 65.
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 2:
            number = "".join(parts)

    try:
        return float(number)
    except ValueError:
        return None


# ==========================================================
# ARCHIVOS
# ==========================================================

def sanitize_filename(value):
    value = clean_text(value) or str(int(time.time()))
    value = re.sub(r"[^a-zA-Z0-9_-]", "_", value)
    return value[:120]


def file_hash(path):
    """SHA-256 del archivo. Devuelve None si no existe."""
    if not path or not Path(path).exists():
        return None

    sha256 = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def get_publication_evidence_dirs(publicacion_id, base_dir, con_screenshots=True):
    """Crea y devuelve las carpetas de evidencia de una publicacion.

    Devuelve (html_dir, img_dir, screenshot_dir). Cuando con_screenshots es
    False, screenshot_dir viene en None: Amorel y Facebook no toman capturas.
    """
    publicacion_dir = Path(base_dir) / f"publicacion_{publicacion_id}"

    html_dir = publicacion_dir / "html"
    img_dir = publicacion_dir / "imagenes"
    screenshot_dir = publicacion_dir / "screenshots" if con_screenshots else None

    for folder in [html_dir, img_dir, screenshot_dir]:
        if folder:
            folder.mkdir(parents=True, exist_ok=True)

    return html_dir, img_dir, screenshot_dir


# ==========================================================
# BASE DE DATOS
# ==========================================================

def get_connection(default_port="3306"):
    if mysql is None:
        raise RuntimeError("mysql-connector-python no esta instalado.")

    return mysql.connector.connect(**get_db_config(default_port))


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
    """Devuelve el id de la publicacion si ya esta guardada, o None.

    Con codigo_externo tambien valida por (fuente_id, codigo_externo): los
    portales reutilizan el mismo codigo bajo URLs distintas.
    """
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


def insert_evidencia(connection, publicacion_id, tipo, ruta_archivo, url_original=None):
    """Guarda una evidencia si no estaba ya registrada, con su hash."""
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

    cursor.execute(
        """
        INSERT INTO evidencias_publicacion
        (publicacion_id, tipo, ruta_archivo, url_original, hash_archivo)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (publicacion_id, tipo, ruta_archivo, url_original, file_hash(ruta_archivo)),
    )
    connection.commit()
    cursor.close()
