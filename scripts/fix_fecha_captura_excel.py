"""Corrige `fecha_captura` de las publicaciones importadas del Excel del cliente.

El importador (import_excel_ventas.py) dejo fecha_captura en su valor por
defecto (el momento de la corrida), y guardo la fecha real del cliente
("fecha actualizacion", o "fecha" como respaldo) solo dentro de
links_adicionales. Este script la mueve a fecha_captura, que es la columna
que se muestra/ordena en el front, para que las publicaciones importadas
aparezcan con su fecha real en vez de "hoy".

Solo toca filas con links_adicionales.fuente_importacion =
"excel_cliente_estudio_mercado" (las que puso import_excel_ventas.py). No
modifica el esquema ni ninguna otra columna.

Uso:
    py -3 scripts/fix_fecha_captura_excel.py            # dry-run
    py -3 scripts/fix_fecha_captura_excel.py --apply    # escribe
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inmobiliary.common import get_connection  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Escribe en MySQL (por defecto es dry-run).")
    args = parser.parse_args()

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, links_adicionales, fecha_captura
        FROM publicaciones
        WHERE JSON_EXTRACT(links_adicionales, '$.fuente_importacion') = 'excel_cliente_estudio_mercado'
        """
    )
    rows = cursor.fetchall()
    cursor.close()

    print(f"[INFO] Publicaciones importadas del Excel encontradas: {len(rows)}")

    via_actualizacion = 0
    via_fecha = 0
    sin_fecha = 0
    updates = []

    for publicacion_id, links_adicionales_raw, fecha_captura_actual in rows:
        data = json.loads(links_adicionales_raw) if links_adicionales_raw else {}
        fecha_actualizacion = data.get("fecha_actualizacion_excel")
        fecha_excel = data.get("fecha_excel")

        elegida = None
        origen = None
        if fecha_actualizacion:
            elegida = fecha_actualizacion
            origen = "fecha_actualizacion_excel"
            via_actualizacion += 1
        elif fecha_excel:
            elegida = fecha_excel
            origen = "fecha_excel"
            via_fecha += 1
        else:
            sin_fecha += 1
            continue

        try:
            fecha_dt = datetime.strptime(elegida, "%Y-%m-%d")
        except ValueError:
            sin_fecha += 1
            continue

        updates.append((publicacion_id, fecha_dt, origen))

    print(f"[INFO] Con fecha_actualizacion_excel: {via_actualizacion}")
    print(f"[INFO] Con fecha_excel (respaldo): {via_fecha}")
    print(f"[INFO] Sin ninguna fecha valida (quedan con fecha de hoy): {sin_fecha}")

    if not args.apply:
        print("\n[DRY-RUN] No se escribio nada. Corre con --apply para aplicar.")
        print("[DRY-RUN] Muestra de 5 cambios:")
        for publicacion_id, fecha_dt, origen in updates[:5]:
            print(f"     - id {publicacion_id}: fecha_captura -> {fecha_dt.date()} (via {origen})")
        connection.close()
        return

    cursor = connection.cursor()
    for publicacion_id, fecha_dt, _origen in updates:
        cursor.execute(
            "UPDATE publicaciones SET fecha_captura = %s WHERE id = %s",
            (fecha_dt, publicacion_id),
        )
    connection.commit()
    cursor.close()
    connection.close()

    print(f"\n[OK] fecha_captura actualizada en {len(updates)} publicaciones.")


if __name__ == "__main__":
    main()
