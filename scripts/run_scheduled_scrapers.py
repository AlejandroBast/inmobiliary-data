"""Orquestador de las corridas automaticas (cron) de los scrapers.

La VM donde vive el servidor tiene recursos limitados, asi que los scrapers
NUNCA corren en paralelo aca: se lanzan uno detras de otro, en orden, y cada
uno espera a que termine el anterior.

Calendario:
  - Lunes: los cinco portales, en orden (fincaraiz, ciencuadras,
    metrocuadrado, amorel, facebook).
  - Viernes: solo Facebook Marketplace, porque el inventario ahi cambia mas
    rapido que en el resto de portales y una sola pasada semanal se queda
    corta.

Si un scraper falla, se registra el error en el log y el orquestador sigue
con el siguiente: perder toda la corrida por un solo portal caido sale mas
caro que dejar un error puntual anotado.

Uso:
    py -3 scripts/run_scheduled_scrapers.py              # segun el dia de hoy
    py -3 scripts/run_scheduled_scrapers.py --day friday # fuerza un dia (pruebas)
    py -3 scripts/run_scheduled_scrapers.py --dry-run     # imprime el plan, no ejecuta nada

Pensado para invocarse desde cron en el servidor, un dia a la vez:
    0 12 * * 1,5 /ruta/al/.venv/bin/python /ruta/al/repo/scripts/run_scheduled_scrapers.py >> /ruta/al/repo/logs/scheduled/cron.log 2>&1
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs" / "scheduled"

# Mismo orden que el panel del front (front/lib/scrapers.ts).
ALL_SCRAPERS = ["fincaraiz", "ciencuadras", "metrocuadrado", "amorel", "facebook"]

SCHEDULE = {
    "monday": ALL_SCRAPERS,
    "friday": ["facebook"],
}

MODULE_BY_SOURCE = {name: f"inmobiliary.scrapers.{name}" for name in ALL_SCRAPERS}

WEEKDAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
]


def resolve_python():
    """Mismo criterio que front/lib/scrapers.ts: SCRAPER_PYTHON manda si esta definida."""
    configured = os.environ.get("SCRAPER_PYTHON", "").strip()
    return configured or sys.executable


def run_source(source_id, python_exe, log_file):
    module = MODULE_BY_SOURCE[source_id]
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": os.pathsep.join(
            part for part in [str(PROJECT_ROOT / "src"), os.environ.get("PYTHONPATH")] if part
        ),
    }

    started = datetime.now()
    header = f"\n=== {source_id} | inicio {started:%Y-%m-%d %H:%M:%S} ==="
    print(header)
    log_file.write(header + "\n")
    log_file.flush()

    process = subprocess.run(
        [python_exe, "-m", module],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    finished = datetime.now()
    duration = (finished - started).total_seconds()
    status = "OK" if process.returncode == 0 else f"ERROR (codigo {process.returncode})"
    footer = f"=== {source_id} | fin {finished:%Y-%m-%d %H:%M:%S} | {status} | {duration:.0f}s ==="
    print(footer)
    log_file.write(footer + "\n")
    log_file.flush()

    return process.returncode == 0, duration


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--day", choices=WEEKDAY_NAMES, help="Forzar el dia (para pruebas). Por defecto usa el dia de hoy.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra que se ejecutaria sin correr nada")
    args = parser.parse_args()

    day = args.day or WEEKDAY_NAMES[datetime.now().weekday()]
    sources = SCHEDULE.get(day, [])

    if not sources:
        print(f"No hay scrapers programados para {day}. Nada que hacer.")
        return 0

    if args.dry_run:
        print(f"[dry-run] {day}: se ejecutarian en orden -> {', '.join(sources)}")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now():%Y-%m-%d}_{day}.log"
    python_exe = resolve_python()

    results = []
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n########## Corrida {day} | {datetime.now():%Y-%m-%d %H:%M:%S} | python={python_exe} ##########\n"
        )
        for source_id in sources:
            ok, duration = run_source(source_id, python_exe, log_file)
            results.append((source_id, ok, duration))

    summary = "\n".join(
        f"  {'OK ' if ok else 'ERR'}  {source_id:<15} {duration:.0f}s" for source_id, ok, duration in results
    )
    failed = [source_id for source_id, ok, _ in results if not ok]
    print(f"\nResumen {day}:\n{summary}")
    print(f"Log completo: {log_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
