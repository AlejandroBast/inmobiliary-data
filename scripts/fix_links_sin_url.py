"""Corrige filas del Excel donde "link" no era una URL real (nombre de
contacto, telefono, nota de campo). El front trataba ese texto como link
relativo y terminaba abriendo localhost/<texto>.

Mueve ese texto a `notas` (agregandolo, sin pisar lo que ya hubiera) y deja
en `link_origen` un placeholder no clickeable (`sin-link://excel-cliente/{id}`)
que satisface NOT NULL UNIQUE sin fingir ser una URL real.

Uso:
    py -3 scripts/fix_links_sin_url.py            # dry-run
    py -3 scripts/fix_links_sin_url.py --apply     # escribe
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inmobiliary.common import get_connection  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, link_origen, notas FROM publicaciones WHERE link_origen NOT LIKE 'http%'"
    )
    rows = cursor.fetchall()
    print(f"[INFO] Filas con link_origen que no es una URL real: {len(rows)}")

    updates = []
    for publicacion_id, link_origen, notas in rows:
        nueva_nota_pieza = f"Contacto/origen sin link online (dato de campo del Excel): {link_origen}"
        nuevas_notas = f"{notas}\n\n{nueva_nota_pieza}" if notas else nueva_nota_pieza
        nuevo_link = f"sin-link://excel-cliente/{publicacion_id}"
        updates.append((publicacion_id, nuevo_link, nuevas_notas))

    if not args.apply:
        print("[DRY-RUN] Muestra de 5:")
        for publicacion_id, nuevo_link, nuevas_notas in updates[:5]:
            print(f"  id {publicacion_id}: link_origen -> {nuevo_link!r} | notas -> {nuevas_notas!r}")
        connection.close()
        return

    for publicacion_id, nuevo_link, nuevas_notas in updates:
        link_check = json.dumps(
            {"ok": None, "detalle": "sin_link_real_dato_de_campo", "verificado_en": None},
            ensure_ascii=False,
        )
        cursor.execute(
            """
            UPDATE publicaciones
            SET link_origen = %s,
                notas = %s,
                links_adicionales = JSON_SET(
                    COALESCE(links_adicionales, JSON_OBJECT()),
                    '$.link_check',
                    CAST(%s AS JSON)
                )
            WHERE id = %s
            """,
            (nuevo_link, nuevas_notas, link_check, publicacion_id),
        )
    connection.commit()
    cursor.close()
    connection.close()
    print(f"[OK] {len(updates)} filas corregidas.")


if __name__ == "__main__":
    main()
