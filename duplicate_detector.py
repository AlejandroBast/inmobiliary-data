"""Deteccion conservadora de varias publicaciones del mismo inmueble.

El modulo nunca elimina publicaciones. Registra candidatos explicables y solo
agrupa automaticamente coincidencias fuertes que incluyen evidencia visual.
"""

import json
import math
import os
import re
import unicodedata
from pathlib import Path

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # El scraper debe seguir funcionando sin esta dependencia.
    Image = None
    UnidentifiedImageError = OSError


ENABLED = os.getenv("DUPLICATE_DETECTION_ENABLED", "true").lower() == "true"
AUTO_THRESHOLD = float(os.getenv("DUPLICATE_AUTO_THRESHOLD", "80"))
REVIEW_THRESHOLD = float(os.getenv("DUPLICATE_REVIEW_THRESHOLD", "60"))
MAX_DISTANCE_METERS = float(os.getenv("DUPLICATE_MAX_DISTANCE_METERS", "100"))
HASH_DISTANCE = int(os.getenv("DUPLICATE_HASH_DISTANCE", "8"))
MIN_IMAGE_WIDTH = int(os.getenv("DUPLICATE_MIN_IMAGE_WIDTH", "200"))
MIN_IMAGE_HEIGHT = int(os.getenv("DUPLICATE_MIN_IMAGE_HEIGHT", "150"))


def normalize_text(value):
    if value is None:
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    replacements = {
        r"\bcarrera\b|\bcra\.?\b|\bcr\.?\b": "kr",
        r"\bcalle\b|\bcl\.?\b": "cl",
        r"\bavenida\b|\bav\.?\b": "av",
        r"\bnumero\b|\bno\.?\b|#": " ",
    }
    for pattern, replacement in replacements.items():
        value = re.sub(pattern, replacement, value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def haversine_meters(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def relative_close(first, second, tolerance=0.10):
    if first in (None, 0) or second in (None, 0):
        return False
    first, second = float(first), float(second)
    return abs(first - second) / max(abs(first), abs(second)) <= tolerance


def dhash64(path):
    """Devuelve (hash hexadecimal, ancho, alto) o None para imagenes no validas."""
    if Image is None:
        raise RuntimeError("Pillow no esta instalado; ejecute: python -m pip install Pillow")
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                return None
            return dhash_image(image), width, height
    except (OSError, UnidentifiedImageError):
        return None


def dhash_image(image):
    """Calcula dHash sobre una imagen PIL ya abierta (util tambien en pruebas)."""
    grayscale = image.convert("L").resize((9, 8))
    if hasattr(grayscale, "get_flattened_data"):
        pixels = list(grayscale.get_flattened_data())
    else:
        pixels = list(grayscale.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            value = (value << 1) | int(left > right)
    return f"{value:016x}"


def hash_distance(first, second):
    return (int(first, 16) ^ int(second, 16)).bit_count()


def score_publications(publication, candidate, image_match=None):
    """Calcula una puntuacion explicable sin penalizar precios diferentes."""
    score = 0.0
    reasons = []
    image_match = image_match or {}
    matches = int(image_match.get("count", 0))
    minimum_hash_distance = image_match.get("minimum_distance")

    if matches:
        image_points = min(50, 40 + (matches - 1) * 5)
        score += image_points
        reasons.append({"signal": "similar_images", "points": image_points, "count": matches,
                        "minimum_hash_distance": minimum_hash_distance})

    distance = haversine_meters(
        publication.get("latitud"), publication.get("longitud"),
        candidate.get("latitud"), candidate.get("longitud"),
    )
    if distance is not None and distance <= MAX_DISTANCE_METERS:
        points = 30 if distance <= 30 else 20
        score += points
        reasons.append({"signal": "near_coordinates", "points": points, "meters": round(distance, 2)})

    address = normalize_text(publication.get("direccion"))
    candidate_address = normalize_text(candidate.get("direccion"))
    if address and candidate_address and address == candidate_address:
        score += 20
        reasons.append({"signal": "same_address", "points": 20})

    if relative_close(publication.get("m2"), candidate.get("m2"), 0.10):
        score += 10
        reasons.append({"signal": "similar_area", "points": 10})

    for field, label in (("habitaciones", "same_bedrooms"), ("banios", "same_bathrooms")):
        if publication.get(field) is not None and publication.get(field) == candidate.get(field):
            score += 5
            reasons.append({"signal": label, "points": 5})

    first_type = normalize_text(publication.get("tipo_inmueble"))
    second_type = normalize_text(candidate.get("tipo_inmueble"))
    if first_type and second_type and first_type != second_type:
        score -= 20
        reasons.append({"signal": "different_property_type", "points": -20})

    return max(0.0, min(100.0, score)), reasons, distance


class DuplicateDetector:
    def __init__(self, connection):
        self.connection = connection

    def schema_available(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute("SHOW TABLES LIKE 'coincidencias_publicaciones'")
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    def process_publication(self, publication_id):
        if not ENABLED:
            return []
        if Image is None:
            raise RuntimeError("Pillow no esta instalado; detector omitido")
        if not self.schema_available():
            raise RuntimeError("falta aplicar migrations/001_duplicate_detection.sql")

        self._calculate_image_hashes(publication_id)
        publication = self._get_publication(publication_id)
        if not publication:
            return []

        results = []
        for candidate in self._candidate_publications(publication):
            # Permite comparar contra evidencias historicas que aun no tienen hash.
            self._calculate_image_hashes(candidate["id"])
            image_match = self._compare_images(publication_id, candidate["id"])
            score, reasons, distance = score_publications(publication, candidate, image_match)
            if score < REVIEW_THRESHOLD:
                continue
            strong_location = any(
                reason["signal"] == "same_address"
                or (reason["signal"] == "near_coordinates" and reason.get("meters", 999) <= 30)
                for reason in reasons
            )
            compatible_area = relative_close(publication.get("m2"), candidate.get("m2"), 0.10) or relative_close(
                publication.get("m2_construido"), candidate.get("m2_construido"), 0.10
            )
            compatible_rooms = (
                publication.get("habitaciones") is not None
                and publication.get("banios") is not None
                and publication.get("habitaciones") == candidate.get("habitaciones")
                and publication.get("banios") == candidate.get("banios")
            )
            structural_confirmation = compatible_area or compatible_rooms
            visual_confirmation = structural_confirmation and (
                image_match["count"] >= 2
                or (image_match["count"] >= 1 and strong_location)
            )
            state = "confirmada" if score >= AUTO_THRESHOLD and visual_confirmation else "pendiente"
            self._save_match(publication_id, candidate["id"], score, state, distance, image_match, reasons)
            if state == "confirmada":
                self._group_publications(publication_id, candidate["id"], score, reasons)
            results.append({"candidate_id": candidate["id"], "score": score, "state": state, "reasons": reasons})
        self.connection.commit()
        return results

    def _get_publication(self, publication_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM publicaciones WHERE id = %s", (publication_id,))
        result = cursor.fetchone()
        cursor.close()
        return result

    def _calculate_image_hashes(self, publication_id):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            """SELECT e.id, e.ruta_archivo FROM evidencias_publicacion e
               LEFT JOIN imagenes_hashes h ON h.evidencia_id = e.id AND h.algoritmo = 'dhash64'
               WHERE e.publicacion_id = %s AND e.tipo = 'imagen' AND h.id IS NULL""",
            (publication_id,),
        )
        images = cursor.fetchall()
        for evidence in images:
            path = Path(evidence["ruta_archivo"] or "")
            if not path.is_file():
                continue
            result = dhash64(path)
            if not result:
                continue
            perceptual_hash, width, height = result
            cursor.execute(
                """INSERT IGNORE INTO imagenes_hashes
                   (evidencia_id, publicacion_id, algoritmo, hash_perceptual, ancho, alto)
                   VALUES (%s, %s, 'dhash64', %s, %s, %s)""",
                (evidence["id"], publication_id, perceptual_hash, width, height),
            )
        cursor.close()

    def _candidate_publications(self, publication):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            """SELECT p.* FROM publicaciones p
               WHERE p.id <> %s
                 AND (p.tipo_inmueble = %s OR %s IS NULL)
                 AND (
                    (p.barrio IS NOT NULL AND LOWER(TRIM(p.barrio)) = LOWER(TRIM(%s)))
                    OR (p.latitud IS NOT NULL AND p.longitud IS NOT NULL AND %s IS NOT NULL AND %s IS NOT NULL)
                    OR EXISTS (SELECT 1 FROM imagenes_hashes h WHERE h.publicacion_id = p.id)
                 )
               ORDER BY p.id DESC LIMIT 500""",
            (publication["id"], publication.get("tipo_inmueble"), publication.get("tipo_inmueble"),
             publication.get("barrio"), publication.get("latitud"), publication.get("longitud")),
        )
        results = cursor.fetchall()
        cursor.close()
        return results

    def _compare_images(self, first_id, second_id):
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT publicacion_id, hash_perceptual FROM imagenes_hashes WHERE publicacion_id IN (%s, %s)",
            (first_id, second_id),
        )
        grouped = {first_id: [], second_id: []}
        for publication_id, value in cursor.fetchall():
            grouped[publication_id].append(value)
        cursor.close()
        pairs = sorted(
            (hash_distance(first_hash, second_hash), first_index, second_index)
            for first_index, first_hash in enumerate(grouped[first_id])
            for second_index, second_hash in enumerate(grouped[second_id])
        )
        used_first = set()
        used_second = set()
        close = []
        for distance, first_index, second_index in pairs:
            if distance > HASH_DISTANCE:
                break
            if first_index in used_first or second_index in used_second:
                continue
            used_first.add(first_index)
            used_second.add(second_index)
            close.append(distance)
        return {"count": len(close), "minimum_distance": pairs[0][0] if pairs else None}

    def _save_match(self, first_id, second_id, score, state, distance, image_match, reasons):
        first_id, second_id = sorted((first_id, second_id))
        cursor = self.connection.cursor()
        cursor.execute(
            """INSERT INTO coincidencias_publicaciones
               (publicacion_id, candidata_id, puntaje, estado, distancia_metros,
                imagenes_coincidentes, distancia_hash_minima, razones)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE puntaje = VALUES(puntaje),
                 estado = IF(estado = 'descartada', estado, VALUES(estado)),
                 distancia_metros = VALUES(distancia_metros),
                 imagenes_coincidentes = VALUES(imagenes_coincidentes),
                 distancia_hash_minima = VALUES(distancia_hash_minima), razones = VALUES(razones)""",
            (first_id, second_id, score, state, distance, image_match["count"],
             image_match["minimum_distance"], json.dumps(reasons, ensure_ascii=False)),
        )
        cursor.close()

    def _group_publications(self, first_id, second_id, score, reasons):
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT publicacion_id, inmueble_id FROM publicaciones_inmueble WHERE publicacion_id IN (%s, %s)",
            (first_id, second_id),
        )
        existing_groups = dict(cursor.fetchall())
        if existing_groups:
            inmueble_id = existing_groups.get(first_id) or existing_groups.get(second_id)
            other_groups = {group_id for group_id in existing_groups.values() if group_id != inmueble_id}
            for other_group in other_groups:
                cursor.execute(
                    "UPDATE IGNORE publicaciones_inmueble SET inmueble_id = %s WHERE inmueble_id = %s",
                    (inmueble_id, other_group),
                )
                cursor.execute("DELETE FROM publicaciones_inmueble WHERE inmueble_id = %s", (other_group,))
                cursor.execute("DELETE FROM inmuebles_detectados WHERE id = %s", (other_group,))
        else:
            cursor.execute("INSERT INTO inmuebles_detectados (estado) VALUES ('automatico')")
            inmueble_id = cursor.lastrowid
        for publication_id in (first_id, second_id):
            cursor.execute(
                """INSERT INTO publicaciones_inmueble (inmueble_id, publicacion_id, puntaje, razones)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE puntaje = GREATEST(puntaje, VALUES(puntaje)),
                     razones = VALUES(razones)""",
                (inmueble_id, publication_id, score, json.dumps(reasons, ensure_ascii=False)),
            )
        cursor.close()


def detect_duplicates_safely(connection, publication_id, logger=print):
    """Punto de integracion seguro: nunca interrumpe el scraper."""
    try:
        matches = DuplicateDetector(connection).process_publication(publication_id)
        for match in matches:
            logger(
                f"[DUPLICADO] Publicacion {publication_id} vs {match['candidate_id']} | "
                f"puntaje {match['score']:.0f} | {match['state']}"
            )
        return matches
    except Exception as error:
        try:
            connection.rollback()
        except Exception:
            pass
        logger(f"[WARN] Detector de duplicados omitido: {error}")
        return []
