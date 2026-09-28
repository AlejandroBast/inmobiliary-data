"""Extrae una publicacion puntual sin guardarla en MySQL.

El script reutiliza los extractores existentes de cada scraper y solo adapta sus
firmas de entrada/salida a un contrato JSON comun para el front.
"""

import argparse
import base64
import json
import os
import sys

# En el flujo de importacion se necesita la galeria completa. El scraper masivo
# conserva su limite operativo, pero el adaptador puntual no debe truncar fotos.
os.environ.setdefault("FACEBOOK_MAX_IMAGES_PER_LISTING", "0")
os.environ.setdefault("GALLERY_MAX_NEXT_CLICKS", "200")

from playwright.sync_api import sync_playwright

from inmobiliary.scrapers import amorel, ciencuadras, facebook, fincaraiz, metrocuadrado


SCRAPERS = {
    "amorel": amorel,
    "ciencuadras": ciencuadras,
    "fincaraiz": fincaraiz,
    "metrocuadrado": metrocuadrado,
    "facebook": facebook,
}


CIENCUADRAS_S3_PREFIX = "https://www-img-cc.s3.amazonaws.com/"
CIENCUADRAS_IMAGE_CDN = "https://images.ciencuadras.com/"


def public_image_url(source_id, image_url):
    # El bucket S3 de Ciencuadras es privado (responde 403); las fotos solo se
    # sirven a traves de su CDN, que recibe bucket/key codificados en base64.
    if source_id == "ciencuadras" and image_url.startswith(CIENCUADRAS_S3_PREFIX):
        key = image_url[len(CIENCUADRAS_S3_PREFIX):].split("?")[0]
        spec = json.dumps({"bucket": "www-img-cc", "key": key}, separators=(",", ":"))
        return CIENCUADRAS_IMAGE_CDN + base64.b64encode(spec.encode()).decode()
    return image_url


def extract_draft(source_id, url):
    module = SCRAPERS[source_id]
    if source_id == "amorel":
        result = module.extract_publication_data(url)
        data, html, image_urls, skip_reason = result
        return data, image_urls, skip_reason

    with sync_playwright() as playwright:
        if source_id == "facebook":
            context = module.open_facebook_context(playwright)
            try:
                page = context.new_page()
                data, html, image_urls, skip_reason = module.extract_publication_data(page, url)
            finally:
                context.close()
            return data, image_urls, skip_reason

        browser = playwright.chromium.launch(headless=module.HEADLESS)
        try:
            page = browser.new_page(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            result = module.extract_publication_data(page, url, None)
            image_urls = module.collect_image_urls(page) if source_id in {"ciencuadras", "fincaraiz"} else []
        finally:
            browser.close()

    if source_id == "ciencuadras":
        data, html = result
        return data, image_urls, None if data else "sin_datos_extraidos"
    if source_id == "fincaraiz":
        data, html, skip_reason = result
        return data, image_urls, skip_reason

    data, html, image_urls = result
    return data, image_urls, None if data else "sin_datos_extraidos"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=sorted(SCRAPERS))
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    data, image_urls, skip_reason = extract_draft(args.source, args.url)
    if not data:
        raise RuntimeError(skip_reason or "El scraper no pudo extraer la publicación.")

    data["fuente_id"] = None
    data["link_origen"] = data.get("link_origen") or args.url
    image_urls = [
        public_image_url(args.source, url.strip())
        for url in image_urls or []
        if isinstance(url, str) and url.strip()
    ]
    payload = {
        "sourceId": args.source,
        "data": data,
        "imageUrls": list(dict.fromkeys(image_urls)),
    }
    # Windows puede ejecutar este proceso con stdout cp1252. JSON ASCII evita
    # que emojis u otros caracteres Unicode del anuncio rompan la respuesta;
    # el parser del frontend los reconstruye al leer las secuencias escapadas.
    print(json.dumps(payload, ensure_ascii=True, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise
