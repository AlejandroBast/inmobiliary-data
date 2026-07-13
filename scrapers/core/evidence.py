import hashlib
import html as html_module
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DEFAULT_EVIDENCE_DIR = Path("evidencias")


def sanitize_filename(value):
    value = value or str(int(time.time()))
    value = re.sub(r"[^a-zA-Z0-9_-]", "_", str(value))
    return value[:120]


def file_hash(path):
    if not path or not Path(path).exists():
        return None

    sha256 = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_publication_evidence_dirs(publicacion_id, evidence_dir=DEFAULT_EVIDENCE_DIR, include_screenshots=True):
    base_dir = Path(evidence_dir) / f"publicacion_{publicacion_id}"
    html_dir = base_dir / "html"
    img_dir = base_dir / "imagenes"
    screenshot_dir = base_dir / "screenshots"

    folders = [html_dir, img_dir]
    if include_screenshots:
        folders.append(screenshot_dir)

    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    return html_dir, img_dir, screenshot_dir


def make_standalone_html(html, page_url):
    if not page_url:
        return html

    base_tag = f'<base href="{html_module.escape(page_url, quote=True)}">'
    meta_tag = '<meta charset="utf-8">'

    if re.search(r"<base\b", html or "", flags=re.IGNORECASE):
        return html

    if re.search(r"<head[^>]*>", html or "", flags=re.IGNORECASE):
        return re.sub(
            r"(<head[^>]*>)",
            rf"\1\n{meta_tag}\n{base_tag}",
            html,
            count=1,
            flags=re.IGNORECASE,
        )

    return f"<!doctype html><html><head>{meta_tag}{base_tag}</head><body>{html}</body></html>"


def save_html(html, codigo_archivo, publicacion_id, page_url=None, prefix="", evidence_dir=DEFAULT_EVIDENCE_DIR):
    html_dir, _, _ = get_publication_evidence_dirs(publicacion_id, evidence_dir=evidence_dir)
    stem = sanitize_filename(codigo_archivo)
    filename = f"{prefix}_{stem}.html" if prefix else f"{stem}.html"
    path = html_dir / filename

    with open(path, "w", encoding="utf-8") as file:
        file.write(make_standalone_html(html, page_url))

    return path


def save_screenshot(page, codigo_archivo, publicacion_id, prefix="", evidence_dir=DEFAULT_EVIDENCE_DIR):
    _, _, screenshot_dir = get_publication_evidence_dirs(publicacion_id, evidence_dir=evidence_dir)
    stem = sanitize_filename(codigo_archivo)
    filename = f"{prefix}_{stem}.png" if prefix else f"{stem}.png"
    path = screenshot_dir / filename

    try:
        page.screenshot(path=str(path), full_page=True)
        return path
    except Exception as error:
        print(f"[WARN] No se pudo guardar screenshot: {error}")
        return None


def download_images_parallel(
    image_urls,
    codigo_archivo,
    publicacion_id,
    download_image_func,
    image_download_workers=6,
    label="fotos",
):
    if not image_urls:
        return []

    workers = max(1, min(image_download_workers, len(image_urls)))
    downloaded = []

    print(f"[INFO] Descargando {len(image_urls)} {label} con {workers} hilos")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_image_func, image_url, codigo_archivo, index, publicacion_id): (index, image_url)
            for index, image_url in enumerate(image_urls, start=1)
        }

        for future in as_completed(futures):
            index, image_url = futures[future]
            try:
                image_path = future.result()
            except Exception as error:
                print(f"[WARN] No se pudo descargar imagen: {image_url} | {error}")
                continue

            if image_path:
                print(f"[OK] Foto descargada {index}/{len(image_urls)}")
                downloaded.append((index, image_url, image_path))

    downloaded.sort(key=lambda item: item[0])
    return downloaded
