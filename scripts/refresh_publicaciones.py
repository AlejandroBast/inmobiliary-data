"""Re-visita publicaciones ya guardadas para detectar links caidos y cambios
de precio/especificaciones desde que se capturaron.

A diferencia de check_and_persist_link_status.py (que solo hace un GET
liviano con `requests` para saber si el link responde), este script reutiliza
la funcion `extract_publication_data` real de cada scraper -- la misma que
usa la corrida normal para publicaciones nuevas -- asi que puede notar que el
vendedor bajo el precio, cambio el area, o que el portal ahora muestra "aviso
no encontrado" aunque siga respondiendo HTTP 200 (algo que un simple chequeo
de status code nunca detecta).

Que hace por cada publicacion ya guardada:
  1. Vuelve a abrir su link_origen con el extractor real del portal.
  2. Si ya no se puede extraer (link caido, publicacion retirada, sesion de
     Facebook vencida), lo deja escrito en links_adicionales.link_check -- el
     front ya sabe pintar de rojo esas filas (ver publicaciones-manager-pro.tsx).
  3. Si se pudo extraer, compara precio y especificaciones contra lo guardado:
       - si el precio cambio, guarda el valor viejo en
         publicacion_precio_historial (migracion 010) y actualiza
         publicaciones.precio.
       - si cambiaron m2/habitaciones/banios/parqueadero/administracion/
         estrato, actualiza esas columnas directamente (sin historial: solo
         el precio lo pidio el cliente).
     Nunca borra un valor ya guardado por un parseo que esta vez no encontro
     el dato: un campo nuevo en None nunca sobreescribe uno viejo que no lo era.

Nunca toca el resto de links_adicionales (fuente_busqueda, normalizacion_
ubicacion, link_check_manual, etc.): usa JSON_SET puntual, igual que
check_and_persist_link_status.py y setManualLinkStatus en el front.

Amorel se revisa con requests puro (extract_publication_data no necesita
navegador). Fincaraiz, Ciencuadras y Metrocuadrado abren un browser Playwright
normal. Facebook reabre su perfil persistente ya logueado
(scrapers.facebook.open_facebook_context) -- si la sesion vencio, la
publicacion queda "no_verificable" (ok=None) en vez de marcarse como caida,
para no confundir sesion vencida con anuncio retirado.

Uso:
    py -3 scripts/refresh_publicaciones.py                    # los 5 portales
    py -3 scripts/refresh_publicaciones.py --only fincaraiz    # un solo portal
    py -3 scripts/refresh_publicaciones.py --limit 20          # prueba acotada
    py -3 scripts/refresh_publicaciones.py --dry-run           # no escribe nada

Pensado para cron semanal junto a run_scheduled_scrapers.py (ver README.md):
    0 14 * * 1 /ruta/.venv/bin/python /ruta/repo/scripts/refresh_publicaciones.py >> /ruta/repo/logs/scheduled/refresh_publicaciones.log 2>&1
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inmobiliary.common import get_connection  # noqa: E402
from inmobiliary.scrapers import amorel, ciencuadras, facebook, fincaraiz, metrocuadrado  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

# Mismo viewport/UA que fincaraiz.py, ciencuadras.py y metrocuadrado.py usan en
# su propio main(): un fingerprint distinto aca podria disparar el anti-bot
# de forma distinta a como se probo el extractor.
BROWSER_VIEWPORT = {"width": 1366, "height": 768}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Especificaciones que se actualizan directo (sin historial). El precio se
# maneja aparte porque ademas escribe en publicacion_precio_historial.
SPEC_FIELDS = ["m2", "m2_construido", "habitaciones", "banios", "parqueadero", "administracion", "estrato"]

MODULE_BY_PORTAL = {
    "fincaraiz": fincaraiz,
    "ciencuadras": ciencuadras,
    "metrocuadrado": metrocuadrado,
    "amorel": amorel,
    "facebook": facebook,
}
# Orden fijo, mismo criterio que run_scheduled_scrapers.py: nunca en paralelo,
# la VM tiene recursos limitados.
PORTAL_ORDER = ["fincaraiz", "ciencuadras", "metrocuadrado", "amorel", "facebook"]
PLAYWRIGHT_PORTALS = {"fincaraiz", "ciencuadras", "metrocuadrado"}

SELECT_COLUMNS = ["id", "fuente_id", "link_origen", "precio"] + SPEC_FIELDS


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=PORTAL_ORDER, help="Revisa un solo portal")
    parser.add_argument("--limit", type=int, default=0, help="Maximo de publicaciones por portal (0 = sin tope)")
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime lo que cambiaria, no escribe en la BD")
    return parser.parse_args()


def value_changed(old, new):
    """True solo cuando `new` trae un valor distinto al guardado.

    Nunca se dispara con new=None: un parseo que esta vez no encontro el dato
    no debe borrar un valor bueno que ya estaba guardado.
    """
    if new is None:
        return False
    if old is None:
        return True
    try:
        return abs(float(old) - float(new)) > 0.01
    except (TypeError, ValueError):
        return old != new


def check_one(portal_name, module, page, pub):
    """Vuelve a extraer una publicacion puntual.

    Devuelve (data|None, reason|None, error|None). `reason` es el motivo que
    devuelve el propio extractor (sin_precio, fuera_de_pasto, login_o_checkpoint,
    etc.); `error` es una excepcion de red/navegacion (link realmente caido).
    """
    link = pub["link_origen"]
    try:
        if portal_name == "amorel":
            data, _html, _images, reason = module.extract_publication_data(link)
        elif portal_name == "facebook":
            data, _html, _images, reason = module.extract_publication_data(page, link)
        elif portal_name == "fincaraiz":
            data, _html, reason = module.extract_publication_data(page, link, pub["fuente_id"])
        elif portal_name == "ciencuadras":
            data, _html = module.extract_publication_data(page, link, pub["fuente_id"])
            reason = None
        elif portal_name == "metrocuadrado":
            data, _html, _images = module.extract_publication_data(page, link, pub["fuente_id"])
            reason = None
        else:
            raise ValueError(f"Portal desconocido: {portal_name}")
        return data, reason, None
    except Exception as error:  # noqa: BLE001 - un link cae por mil motivos distintos
        return None, None, error


# Motivos que SI son evidencia de que la publicacion ya no esta disponible
# (pagina vacia o sin precio, tipico de un "aviso no encontrado" que sigue
# respondiendo 200 -- el caso que el chequeo liviano de status code no puede
# detectar). Ciencuadras y Metrocuadrado no distinguen el motivo (su
# extract_publication_data siempre devuelve reason=None aqui): entre sus dos
# unicos disparadores posibles (sin_precio, fuera_de_pasto), sin_precio es
# muchisimo mas probable para una fila que ya estaba aceptada como Pasto, asi
# que None se trata igual que un removido.
REMOVED_REASONS = {"sin_precio", "sin_contenido_publicacion", None}
# Sesion de Facebook vencida: no dice nada sobre si la publicacion sigue viva.
SESSION_REASONS = {"login_o_checkpoint"}
# fuera_de_pasto, categoria_no_es_venta, oferta_mixta_no_es_venta_pura, etc.:
# la pagina sigue viva, solo cambio de categoria/ciudad declarada o el filtro
# de negocio la rechaza ahora. Confundir esto con "link caido" generaria
# falsos positivos (visto en pruebas: un anuncio paso a "oferta mixta" y
# seguia perfectamente activo) -- se marca no verificable para que quede
# visible sin pintarse de rojo por error.


def classify(data, reason, error):
    """(ok, detalle) en el mismo formato que links_adicionales.link_check."""
    if error is not None:
        return False, str(error)[:150]
    if data is not None:
        return True, "Re-verificado: la publicacion sigue activa"
    if reason in SESSION_REASONS:
        return None, "Sesion de Facebook vencio; no se pudo verificar esta publicacion"
    if reason in REMOVED_REASONS:
        return False, f"Ya no se pudo extraer la publicacion (motivo: {reason or 'sin_precio_o_ubicacion'})"
    return None, f"Ya no cumple los criterios de venta en Pasto (motivo: {reason}); revisar manualmente"


def persist_link_check(cursor, publicacion_id, ok, detalle, checked_at):
    link_check = json.dumps({"ok": ok, "detalle": detalle, "verificado_en": checked_at}, ensure_ascii=False)
    cursor.execute(
        """
        UPDATE publicaciones
        SET links_adicionales = JSON_SET(COALESCE(links_adicionales, JSON_OBJECT()), '$.link_check', CAST(%s AS JSON))
        WHERE id = %s
        """,
        (link_check, publicacion_id),
    )


def apply_changes(cursor, pub, data):
    """Compara `data` (recien extraido) contra `pub` (fila actual) y actualiza
    lo que cambio. Devuelve (precio_cambio, specs_cambiaron)."""
    sets, values = [], []

    precio_changed = value_changed(pub.get("precio"), data.get("precio"))
    if precio_changed:
        cursor.execute(
            """
            INSERT INTO publicacion_precio_historial (publicacion_id, precio_anterior, precio_nuevo)
            VALUES (%s, %s, %s)
            """,
            (pub["id"], pub.get("precio"), data["precio"]),
        )
        sets.append("precio = %s")
        values.append(data["precio"])

    specs_changed = False
    for field in SPEC_FIELDS:
        if value_changed(pub.get(field), data.get(field)):
            specs_changed = True
            sets.append(f"{field} = %s")
            values.append(data[field])

    if sets:
        values.append(pub["id"])
        cursor.execute(f"UPDATE publicaciones SET {', '.join(sets)} WHERE id = %s", tuple(values))

    return precio_changed, specs_changed


def fetch_publicaciones(connection, fuente_id, limit):
    cursor = connection.cursor(dictionary=True)
    query = f"SELECT {', '.join(SELECT_COLUMNS)} FROM publicaciones WHERE fuente_id = %s ORDER BY id"
    if limit:
        query += " LIMIT %s"
        cursor.execute(query, (fuente_id, limit))
    else:
        cursor.execute(query, (fuente_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def process_portal(connection, portal_name, page, pubs, dry_run):
    module = MODULE_BY_PORTAL[portal_name]
    stats = {"revisadas": 0, "activas": 0, "caidas": 0, "no_verificables": 0,
              "cambio_precio": 0, "cambio_specs": 0, "errores": 0}

    for index, pub in enumerate(pubs, start=1):
        print(f"[INFO] [{portal_name}] {index}/{len(pubs)} -> {pub['link_origen']}")
        data, reason, error = check_one(portal_name, module, page, pub)
        ok, detalle = classify(data, reason, error)
        checked_at = datetime.now().isoformat(timespec="seconds")

        stats["revisadas"] += 1
        if error is not None:
            stats["errores"] += 1
        if ok is True:
            stats["activas"] += 1
        elif ok is False:
            stats["caidas"] += 1
            print(f"[WARN] [{portal_name}] Publicacion {pub['id']} caida: {detalle}")
        else:
            stats["no_verificables"] += 1

        if dry_run:
            if data is not None:
                precio_changed = value_changed(pub.get("precio"), data.get("precio"))
                specs_changed = any(value_changed(pub.get(f), data.get(f)) for f in SPEC_FIELDS)
                if precio_changed:
                    print(f"[DRY-RUN] Publicacion {pub['id']}: precio {pub.get('precio')} -> {data.get('precio')}")
                if specs_changed:
                    print(f"[DRY-RUN] Publicacion {pub['id']}: specs cambiarian")
            continue

        cursor = connection.cursor()
        try:
            persist_link_check(cursor, pub["id"], ok, detalle, checked_at)
            if data is not None:
                precio_changed, specs_changed = apply_changes(cursor, pub, data)
                if precio_changed:
                    stats["cambio_precio"] += 1
                    print(f"[CAMBIO] Publicacion {pub['id']}: precio {pub.get('precio')} -> {data.get('precio')}")
                if specs_changed:
                    stats["cambio_specs"] += 1
                    print(f"[CAMBIO] Publicacion {pub['id']}: especificaciones actualizadas")
            connection.commit()
        except Exception as db_error:
            connection.rollback()
            print(f"[ERROR] Publicacion {pub['id']}: no se pudo guardar el resultado: {db_error}")
        finally:
            cursor.close()

    return stats


def print_stats(portal_name, stats):
    print(
        f"[RESUMEN] {portal_name}: {stats['revisadas']} revisadas | "
        f"{stats['activas']} activas | {stats['caidas']} caidas | "
        f"{stats['no_verificables']} no verificables | "
        f"{stats['cambio_precio']} con cambio de precio | "
        f"{stats['cambio_specs']} con cambio de especificaciones | "
        f"{stats['errores']} errores de red"
    )


def main():
    args = parse_args()
    portals = [args.only] if args.only else PORTAL_ORDER

    connection = get_connection()
    totals = {"revisadas": 0, "activas": 0, "caidas": 0, "no_verificables": 0,
              "cambio_precio": 0, "cambio_specs": 0, "errores": 0}

    for portal_name in portals:
        module = MODULE_BY_PORTAL[portal_name]
        fuente_id = module.get_or_create_fuente_id(connection)
        pubs = fetch_publicaciones(connection, fuente_id, args.limit)
        print(f"\n[INFO] === {portal_name} ({len(pubs)} publicaciones a revisar) ===")
        if not pubs:
            continue

        try:
            if portal_name == "amorel":
                stats = process_portal(connection, portal_name, None, pubs, args.dry_run)
            elif portal_name == "facebook":
                if sync_playwright is None:
                    raise RuntimeError("playwright no esta instalado")
                with sync_playwright() as playwright:
                    context = module.open_facebook_context(playwright)
                    try:
                        page = context.new_page()
                        stats = process_portal(connection, portal_name, page, pubs, args.dry_run)
                    finally:
                        context.close()
            elif portal_name in PLAYWRIGHT_PORTALS:
                if sync_playwright is None:
                    raise RuntimeError("playwright no esta instalado")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        context = browser.new_context(viewport=BROWSER_VIEWPORT, user_agent=BROWSER_USER_AGENT)
                        page = context.new_page()
                        stats = process_portal(connection, portal_name, page, pubs, args.dry_run)
                    finally:
                        browser.close()
            else:
                raise ValueError(f"Portal desconocido: {portal_name}")
        except Exception as error:
            # Un portal caido (perfil de Facebook corrupto, Playwright sin
            # instalar, etc.) no debe frenar la revision de los demas -- mismo
            # criterio que run_scheduled_scrapers.py.
            print(f"[ERROR] {portal_name}: la revision no pudo completarse: {error}")
            continue

        print_stats(portal_name, stats)
        for key in totals:
            totals[key] += stats[key]

    connection.close()
    print("\n[RESUMEN GLOBAL]")
    print_stats("todos los portales", totals)


if __name__ == "__main__":
    main()
