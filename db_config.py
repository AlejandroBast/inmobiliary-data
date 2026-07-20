"""Configuracion unica de conexion a MySQL para scrapers y scripts."""

import os

from dotenv import load_dotenv


load_dotenv()


def get_db_config(default_port="3306"):
    """Devuelve el dict de conexion a MySQL leyendo el entorno o el .env.

    Falla explicitamente si no hay DB_PASSWORD. No existe clave por defecto a
    proposito: los fallbacks hardcodeados que habia antes quedaron expuestos en
    el historial publico del repositorio.
    """
    password = os.getenv("DB_PASSWORD")

    if not password:
        raise RuntimeError(
            "Falta DB_PASSWORD. Definila antes de ejecutar:\n"
            "  .env:       DB_PASSWORD=tu_clave_mysql\n"
            "  PowerShell: $env:DB_PASSWORD=\"tu_clave_mysql\""
        )

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", default_port)),
        "user": os.getenv("DB_USER", "root"),
        "password": password,
        "database": os.getenv("DB_NAME", "db_inmobiliary_data"),
    }
