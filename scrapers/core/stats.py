NO_VENTA_REASONS = {"no_es_venta_pura", "sin_palabra_venta", "no_venta"}


def skip_bucket(reason):
    if reason == "sin_precio":
        return "sin_precio"
    if reason == "sin_barrio":
        return "sin_barrio"
    if reason in NO_VENTA_REASONS:
        return "no_venta"
    return "error"


def print_scraper_summary(
    fuente,
    total_encontrado,
    guardadas,
    descartadas_sin_precio,
    descartadas_no_venta,
    descartadas_sin_barrio,
    duplicadas,
    errores,
):
    print(f"[RESUMEN] Fuente revisada: {fuente}")
    print(f"[RESUMEN] Total encontrado: {total_encontrado}")
    print(f"[RESUMEN] Guardadas: {guardadas}")
    print(f"[RESUMEN] Descartadas sin precio: {descartadas_sin_precio}")
    print(f"[RESUMEN] Descartadas no venta: {descartadas_no_venta}")
    print(f"[RESUMEN] Descartadas sin barrio: {descartadas_sin_barrio}")
    print(f"[RESUMEN] Duplicadas: {duplicadas}")
    print(f"[RESUMEN] Errores: {errores}")
