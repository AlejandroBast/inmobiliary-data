"""Verifica en paralelo si los link_origen de `publicaciones` siguen disponibles.

Solo lee la base y hace GET a cada link; no escribe nada en MySQL ni en el
Excel. Los links de Facebook se marcan aparte como "no verificable" sin
intentar la peticion: sin cookies de sesion exportadas por el scraper,
Facebook siempre redirige a login y el resultado no seria confiable.

Uso:
    py -3 scripts/check_links_disponibles.py
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
        return publicacion_id, link, None, "sin_sesion_facebook"

    try:
        response = requests.get(
            link,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        )
        ok = 200 <= response.status_code < 400
        return publicacion_id, link, ok, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return publicacion_id, link, False, "timeout"
    except Exception as error:
        return publicacion_id, link, False, str(error)[:150]


def main():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT p.id, p.link_origen, f.nombre
        FROM publicaciones p
        JOIN fuentes_inmobiliarias f ON f.id = p.fuente_id
        ORDER BY p.id
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    print(f"[INFO] Total publicaciones a verificar: {len(rows)}")

    resultados = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(check_link, publicacion_id, link): (publicacion_id, link, fuente)
            for publicacion_id, link, fuente in rows
        }
        done = 0
        for future in as_completed(futures):
            publicacion_id, link, fuente = futures[future]
            _, _, ok, detail = future.result()
            resultados.append({"id": publicacion_id, "fuente": fuente, "link": link, "ok": ok, "detalle": detail})
            done += 1
            if done % 200 == 0:
                print(f"[INFO] Verificados {done}/{len(rows)}")

    disponibles = [r for r in resultados if r["ok"] is True]
    caidos = [r for r in resultados if r["ok"] is False]
    no_verificables = [r for r in resultados if r["ok"] is None]

    por_fuente = {}
    for r in resultados:
        stats = por_fuente.setdefault(r["fuente"], {"disponible": 0, "caido": 0, "no_verificable": 0})
        if r["ok"] is True:
            stats["disponible"] += 1
        elif r["ok"] is False:
            stats["caido"] += 1
        else:
            stats["no_verificable"] += 1

    report = {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "total": len(resultados),
        "disponibles": len(disponibles),
        "caidos": len(caidos),
        "no_verificables": len(no_verificables),
        "por_fuente": por_fuente,
        "links_caidos": caidos,
    }

    logs_dir = ROOT / "logs" / "check_links"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_path = logs_dir / f"check_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[OK] Disponibles: {len(disponibles)}")
    print(f"[OK] Caidos: {len(caidos)}")
    print(f"[OK] No verificables (Facebook sin sesion): {len(no_verificables)}")
    print("[OK] Por fuente:")
    for fuente, stats in por_fuente.items():
        print(f"     - {fuente}: disponible={stats['disponible']} caido={stats['caido']} no_verificable={stats['no_verificable']}")
    print(f"[OK] Reporte completo guardado en: {out_path}")


if __name__ == "__main__":
    main()
