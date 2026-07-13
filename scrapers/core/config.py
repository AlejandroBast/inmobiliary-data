import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError as error:  # pragma: no cover - exercised before pytest deps exist
    raise SystemExit(
        "[CONFIG] Falta instalar python-dotenv. Ejecuta: pip install -r requirements.txt"
    ) from error


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env.local"
REQUIRED_DB_ENV_VARS = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")


def get_db_config():
    load_dotenv(ENV_PATH, override=False)

    missing = [name for name in REQUIRED_DB_ENV_VARS if not os.getenv(name)]
    if missing:
        missing_list = ", ".join(missing)
        raise SystemExit(
            "[CONFIG] Faltan variables obligatorias en .env.local o el entorno: "
            f"{missing_list}. Copia .env.local.example a .env.local y completa los valores."
        )

    try:
        port = int(os.environ["DB_PORT"])
    except ValueError as error:
        raise SystemExit("[CONFIG] DB_PORT debe ser un numero entero.") from error

    return {
        "host": os.environ["DB_HOST"],
        "port": port,
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
    }
