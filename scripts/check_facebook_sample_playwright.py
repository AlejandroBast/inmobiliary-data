"""Verifica una muestra de links de Facebook Marketplace con un navegador real.

A diferencia de check_and_persist_link_status.py (que no puede con Facebook:
un fetch liviano siempre choca con su deteccion de bots), esto reutiliza el
mismo perfil persistente de Chromium que ya uso el scraper para loguearse, y
navega de verdad cada link. Por diseno se limita a una muestra chica: revisar
los ~2700 uno por uno tardaria horas y arriesga que Facebook marque la cuenta
por visitar miles de publicaciones seguidas en poco tiempo.

Guarda el resultado en publicaciones.links_adicionales.link_check, igual que
el chequeo liviano, para que el front los pinte en rojo/gris sin cambios
adicionales.

Uso:
    py -3 scripts/check_facebook_sample_playwright.py [cantidad]
    (cantidad por defecto: 40)
"""

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inmobiliary.common import get_connection  # noqa: E402

PROFILE_DIR = ROOT / ".facebook_profile_2"
PAGE_TIMEOUT_MS = 20000
PAUSE_BETWEEN_SECONDS = 2.5

UNAVAILABLE_MARKERS = [
    "content isn't available",
    "contenido no está disponible",
    "this content isn't available right now",
    "page not found",
    "página no encontrada",
]
LOGIN_MARKERS = ["log in to facebook", "iniciar sesión", "checkpoint"]


def classify(page):
    url = page.url.lower()
    if "/login" in url or "/checkpoint" in url:
        return None, "sesion_perdida_durante_el_chequeo"

    try:
        body = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        body = ""

    if any(marker in body for marker in LOGIN_MARKERS):
        return None, "sesion_perdida_durante_el_chequeo"
    if any(marker in body for marker in UNAVAILABLE_MARKERS):
        return False, "contenido_no_disponible"
    return True, "contenido_visible"


def main():
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 40

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT id, link_origen FROM publicaciones WHERE link_origen LIKE %s", ("%facebook.com%",))
    all_links = cursor.fetchall()

    # No repetir publicaciones ya revisadas con este mismo metodo en corridas anteriores.
    cursor.execute(
        """
        SELECT id FROM publicaciones
        WHERE link_origen LIKE %s
          AND JSON_EXTRACT(links_adicionales, '$.link_check.metodo') = 'playwright_muestra'
        """,
        ("%facebook.com%",),
    )
    ya_revisadas = {row[0] for row in cursor.fetchall()}
    cursor.close()

    pendientes = [(pid, link) for pid, link in all_links if pid not in ya_revisadas]
    sample = random.sample(pendientes, min(sample_size, len(pendientes)))
    print(f"[INFO] Total links de Facebook: {len(all_links)}. Ya revisados antes: {len(ya_revisadas)}. Muestra nueva: {len(sample)}")

    resultados = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            locale="es-CO",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()

        for index, (publicacion_id, link) in enumerate(sample, start=1):
            print(f"[INFO] {index}/{len(sample)}: publicacion {publicacion_id}")
            try:
                page.goto(link, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                page.wait_for_timeout(1500)
                ok, detalle = classify(page)
            except Exception as error:
                ok, detalle = None, f"error_navegando: {str(error)[:120]}"

            resultados.append((publicacion_id, ok, detalle))
            print(f"     -> ok={ok} detalle={detalle}")

            if detalle == "sesion_perdida_durante_el_chequeo":
                print("[WARN] La sesion se perdio a mitad de la corrida. Se corta aca para no seguir a ciegas.")
                break

            time.sleep(PAUSE_BETWEEN_SECONDS)

        context.close()

    checked_at = datetime.now().isoformat(timespec="seconds")
    cursor = connection.cursor()
    for publicacion_id, ok, detalle in resultados:
        link_check = json.dumps(
            {"ok": ok, "detalle": detalle, "verificado_en": checked_at, "metodo": "playwright_muestra"},
            ensure_ascii=False,
        )
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

    disponibles = sum(1 for _, ok, _ in resultados if ok is True)
    caidos = sum(1 for _, ok, _ in resultados if ok is False)
    inciertos = sum(1 for _, ok, _ in resultados if ok is None)
    print(f"\n[OK] Muestra revisada: {len(resultados)}")
    print(f"[OK] Disponibles: {disponibles}")
    print(f"[OK] Caidos (contenido no disponible): {caidos}")
    print(f"[OK] Inciertos (sesion perdida/error): {inciertos}")
    if disponibles + caidos:
        print(f"[OK] Estimado de caidos sobre el total de Facebook ({len(all_links)}): {caidos / (disponibles + caidos):.0%}")


if __name__ == "__main__":
    main()
