"""Verifica los link_origen y guarda el resultado en `links_adicionales`.

A diferencia de check_links_disponibles.py (que solo genera un reporte), este
script SI escribe en la base: agrega la clave "link_check" dentro del JSON
`links_adicionales` de cada publicacion, sin tocar el resto de esa columna ni
ninguna otra. El front la lee para pintar en rojo las filas con link caido
sin depender del chequeo en vivo del navegador (que requiere esperar y solo
cubre la pagina visible).

Los links de Facebook se marcan como "no_verificable" sin intentar la
peticion (necesitan sesion logueada, que no tenemos desde este script).

Uso:
    py -3 scripts/check_and_persist_link_status.py
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inmobiliary.common import get_connection  # noqa: E402

WORKERS = 20
TIMEOUT_SECONDS = 8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
FACEBOOK_RE = re.compile(r"facebook\.com", re.IGNORECASE)


def check_link(publicacion_id, link):
    if FACEBOOK_RE.search(link or ""):
        return publicacion_id, None, "no_verificable_sin_sesion_facebook"
    try:
        response = requests.get(
            link,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        )
        ok = 200 <= response.status_code < 400
        return publicacion_id, ok, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return publicacion_id, False, "timeout"
    except Exception as error:
        return publicacion_id, False, str(error)[:150]


def main():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id, link_origen FROM publicaciones ORDER BY id")
    rows = cursor.fetchall()
    cursor.close()

    print(f"[INFO] Total publicaciones a verificar: {len(rows)}")

    resultados = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(check_link, pid, link): pid for pid, link in rows}
        done = 0
        for future in as_completed(futures):
            publicacion_id, ok, detalle = future.result()
            resultados[publicacion_id] = (ok, detalle)
            done += 1
            if done % 300 == 0:
                print(f"[INFO] Verificados {done}/{len(rows)}")

    checked_at = datetime.now().isoformat(timespec="seconds")
    cursor = connection.cursor()
    disponibles = caidos = no_verificables = 0
    for publicacion_id, (ok, detalle) in resultados.items():
        if ok is True:
            disponibles += 1
        elif ok is False:
            caidos += 1
        else:
            no_verificables += 1

        link_check = json.dumps({"ok": ok, "detalle": detalle, "verificado_en": checked_at}, ensure_ascii=False)
        cursor.execute(
            """
            UPDATE publicaciones
            SET links_adicionales = JSON_SET(
                COALESCE(links_adicionales, JSON_OBJECT()),
                '$.link_check',
                CAST(%s AS JSON)
            )
            WHERE id = %s
            """,
            (link_check, publicacion_id),
        )
    connection.commit()
    cursor.close()
    connection.close()

    print(f"\n[OK] Disponibles: {disponibles}")
    print(f"[OK] Caidos: {caidos}")
    print(f"[OK] No verificables (Facebook sin sesion): {no_verificables}")
    print("[OK] Resultado guardado en publicaciones.links_adicionales.link_check para cada fila.")


if __name__ == "__main__":
    main()
