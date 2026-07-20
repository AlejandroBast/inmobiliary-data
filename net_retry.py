"""Reintentos con backoff para las operaciones de red de los scrapers."""

import os
import time


RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
RETRY_BASE_DELAY_SECONDS = float(os.getenv("RETRY_BASE_DELAY_SECONDS", "2"))


def with_retry(operation, description, attempts=None, base_delay=None):
    """Ejecuta operation() reintentando con backoff exponencial.

    Devuelve lo que devuelva operation(). Si se agotan los intentos relanza la
    ultima excepcion, para que el que llama siga decidiendo si descarta el item
    o corta la corrida: esto solo agrega reintentos, no cambia ese criterio.
    """
    attempts = attempts or RETRY_ATTEMPTS
    base_delay = RETRY_BASE_DELAY_SECONDS if base_delay is None else base_delay

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            if attempt == attempts:
                print(f"[ERROR] {description}: descartado tras {attempts} intentos | {error}")
                raise

            delay = base_delay * (2 ** (attempt - 1))
            print(
                f"[WARN] {description}: intento {attempt}/{attempts} fallo ({error}). "
                f"Reintenta en {delay:.0f}s"
            )
            time.sleep(delay)
