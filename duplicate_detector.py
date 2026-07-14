"""Deteccion conservadora de varias publicaciones del mismo inmueble.

El modulo nunca elimina publicaciones. Registra candidatos explicables y solo
agrupa automaticamente coincidencias fuertes que incluyen evidencia visual.
"""

import hashlib
import json
import math
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None

load_dotenv()

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # El scraper debe seguir funcionando sin esta dependencia.
    Image = None
    UnidentifiedImageError = OSError


ENABLED = os.getenv("DUPLICATE_DETECTION_ENABLED", "true").lower() == "true"
AUTO_THRESHOLD = float(os.getenv("DUPLICATE_AUTO_THRESHOLD", "80"))
REVIEW_THRESHOLD = float(os.getenv("DUPLICATE_REVIEW_THRESHOLD", "60"))
MAX_DISTANCE_METERS = float(os.getenv("DUPLICATE_MAX_DISTANCE_METERS", "100"))
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


def text_similarity(first, second):
    first = normalize_text(first)
    second = normalize_text(second)
    if not first or not second:
        return 0.0
    return SequenceMatcher(None, first, second).ratio()


def comparable_values(first, second):
    return first is not None and second is not None


def add_reason(reasons, signal, points, **details):
    reasons.append({"signal": signal, "points": points, **details})
    return points


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


def sha256_stream(file):
    """Hash criptografico de un flujo binario."""
    digest = hashlib.sha256()
    for chunk in iter(lambda: file.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path):
    """Hash criptografico del archivo completo para igualdad byte por byte."""
    with Path(path).open("rb") as file:
        return sha256_stream(file)


def score_publications(publication, candidate, image_match=None):
    """Puntua coincidencias y contradicciones usando todos los campos utiles."""
    score = 0.0
    reasons = []
    image_match = image_match or {}
    matches = int(image_match.get("count", 0))
    minimum_hash_distance = image_match.get("minimum_distance")

    if matches:
        image_points = min(50, 40 + (matches - 1) * 5)
        score += image_points
        add_reason(reasons, "identical_images", image_points, count=matches,
                   minimum_hash_distance=minimum_hash_distance)

    distance = haversine_meters(
        publication.get("latitud"), publication.get("longitud"),
        candidate.get("latitud"), candidate.get("longitud"),
    )
    if distance is not None and distance <= MAX_DISTANCE_METERS:
        points = 30 if distance <= 30 else 20
        score += points
        add_reason(reasons, "near_coordinates", points, meters=round(distance, 2))
    elif distance is not None and distance > 1000:
        score -= 35
        add_reason(reasons, "distant_coordinates", -35, meters=round(distance, 2))

    address = normalize_text(publication.get("direccion"))
    candidate_address = normalize_text(candidate.get("direccion"))
    if address and candidate_address and address == candidate_address:
        score += 20
        add_reason(reasons, "same_address", 20)
    elif address and candidate_address:
        similarity = text_similarity(address, candidate_address)
        if similarity >= 0.82:
            score += 12
            add_reason(reasons, "similar_address", 12, similarity=round(similarity, 3))

    for field, same_signal, different_signal, same_points, different_points in (
        ("ciudad", "same_city", "different_city", 3, -40),
        ("barrio", "same_neighborhood", "different_neighborhood", 6, -8),
        ("tipo_inmueble", "same_property_type", "different_property_type", 4, -30),
        ("ph", "same_building", "different_building", 8, -10),
        ("antiguedad", "same_age", "different_age", 2, -2),
    ):
        first = normalize_text(publication.get(field))
        second = normalize_text(candidate.get(field))
        if not first or not second:
            continue
        if first == second:
            score += same_points
            add_reason(reasons, same_signal, same_points)
        elif field in {"ciudad", "tipo_inmueble", "ph"} or text_similarity(first, second) < 0.65:
            score += different_points
            add_reason(reasons, different_signal, different_points)

    if relative_close(publication.get("m2"), candidate.get("m2"), 0.10):
        score += 10
        add_reason(reasons, "similar_area", 10)
    elif comparable_values(publication.get("m2"), candidate.get("m2")) and not relative_close(
        publication.get("m2"), candidate.get("m2"), 0.25
    ):
        score -= 15
        add_reason(reasons, "different_area", -15)

    if relative_close(publication.get("m2_construido"), candidate.get("m2_construido"), 0.10):
        score += 7
        add_reason(reasons, "similar_built_area", 7)
    elif comparable_values(publication.get("m2_construido"), candidate.get("m2_construido")) and not relative_close(
        publication.get("m2_construido"), candidate.get("m2_construido"), 0.25
    ):
        score -= 10
        add_reason(reasons, "different_built_area", -10)

    for field, same_signal, different_signal, same_points, different_points in (
        ("habitaciones", "same_bedrooms", "different_bedrooms", 5, -8),
        ("banios", "same_bathrooms", "different_bathrooms", 5, -8),
        ("parqueadero", "same_parking", "different_parking", 3, -4),
        ("estrato", "same_stratum", "different_stratum", 3, -5),
        ("pisos", "same_floors", "different_floors", 2, -3),
    ):
        first = publication.get(field)
        second = candidate.get(field)
        if not comparable_values(first, second):
            continue
        points = same_points if first == second else different_points
        score += points
        add_reason(reasons, same_signal if first == second else different_signal, points)

    for field, signal, tolerance, points in (
        ("precio", "similar_price", 0.15, 3),
        ("administracion", "similar_administration", 0.15, 2),
    ):
        if relative_close(publication.get(field), candidate.get(field), tolerance):
            score += points
            add_reason(reasons, signal, points)

    description_similarity = text_similarity(publication.get("descripcion"), candidate.get("descripcion"))
    if description_similarity >= 0.88:
        score += 8
        add_reason(reasons, "very_similar_description", 8, similarity=round(description_similarity, 3))
    elif description_similarity >= 0.72:
        score += 4
        add_reason(reasons, "similar_description", 4, similarity=round(description_similarity, 3))

    return max(0.0, min(100.0, score)), reasons, distance


class DuplicateDetector:
    def __init__(self, connection):
        self.connection = connection

    def schema_available(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_schema = DATABASE()
                     AND table_name = 'imagenes_hashes'
                     AND column_name = 'hash_contenido'"""
            )
            has_content_hash = cursor.fetchone()[0] == 1
            cursor.execute("SHOW TABLES LIKE 'coincidencias_publicaciones'")
            return has_content_hash and cursor.fetchone() is not None
        finally:
            cursor.close()

    def process_publication(self, publication_id):
        if not ENABLED:
            return []
        if Image is None:
            raise RuntimeError("Pillow no esta instalado; detector omitido")
        if not self.schema_available():
            raise RuntimeError("falta aplicar las migraciones del detector de duplicados")

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
            signals = {reason["signal"] for reason in reasons}
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
            hard_conflict = bool(signals & {
                "different_city",
                "different_property_type",
                "distant_coordinates",
                "different_area",
                "different_built_area",
            })
            visual_confirmation = structural_confirmation and (
                image_match["count"] >= 2
                or (image_match["count"] >= 1 and strong_location)
            )
            state = (
                "confirmada"
                if score >= AUTO_THRESHOLD and visual_confirmation and not hard_conflict
                else "pendiente"
            )
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
               WHERE e.publicacion_id = %s AND e.tipo = 'imagen'
                 AND (h.id IS NULL OR h.hash_contenido IS NULL)""",
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
            content_hash = sha256_file(path)
            cursor.execute(
                """INSERT INTO imagenes_hashes
                   (evidencia_id, publicacion_id, algoritmo, hash_perceptual,
                    hash_contenido, ancho, alto)
                   VALUES (%s, %s, 'dhash64', %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     hash_perceptual = VALUES(hash_perceptual),
                     hash_contenido = VALUES(hash_contenido),
                     ancho = VALUES(ancho), alto = VALUES(alto)""",
                (evidence["id"], publication_id, perceptual_hash, content_hash, width, height),
            )
        cursor.close()

    def _candidate_publications(self, publication):
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute(
            """SELECT p.* FROM publicaciones p
               WHERE p.id <> %s
                 AND (p.ciudad IS NULL OR %s IS NULL OR LOWER(TRIM(p.ciudad)) = LOWER(TRIM(%s)))
                 AND (
                    (p.barrio IS NOT NULL AND LOWER(TRIM(p.barrio)) = LOWER(TRIM(%s)))
                    OR (p.direccion IS NOT NULL AND LOWER(TRIM(p.direccion)) = LOWER(TRIM(%s)))
                    OR (p.latitud IS NOT NULL AND p.longitud IS NOT NULL AND %s IS NOT NULL AND %s IS NOT NULL)
                    OR EXISTS (SELECT 1 FROM imagenes_hashes h WHERE h.publicacion_id = p.id)
                 )
               ORDER BY p.id DESC LIMIT 1000""",
            (publication["id"], publication.get("ciudad"), publication.get("ciudad"),
             publication.get("barrio"), publication.get("direccion"),
             publication.get("latitud"), publication.get("longitud")),
        )
        results = cursor.fetchall()
        cursor.close()
        return results

    def _compare_images(self, first_id, second_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """SELECT publicacion_id, hash_contenido, hash_perceptual
               FROM imagenes_hashes WHERE publicacion_id IN (%s, %s)""",
            (first_id, second_id),
        )
        grouped = {first_id: [], second_id: []}
        perceptual = {first_id: [], second_id: []}
        for publication_id, content_hash, perceptual_hash in cursor.fetchall():
            if content_hash:
                grouped[publication_id].append(content_hash)
            if perceptual_hash:
                perceptual[publication_id].append(perceptual_hash)
        cursor.close()
        pairs = [
            (first_index, second_index)
            for first_index, first_hash in enumerate(grouped[first_id])
            for second_index, second_hash in enumerate(grouped[second_id])
            if first_hash == second_hash
        ]
        used_first = set()
        used_second = set()
        exact = []
        for first_index, second_index in pairs:
            if first_index in used_first or second_index in used_second:
                continue
            used_first.add(first_index)
            used_second.add(second_index)
            exact.append((first_index, second_index))
        perceptual_distances = [
            hash_distance(first_hash, second_hash)
            for first_hash in perceptual[first_id]
            for second_hash in perceptual[second_id]
        ]
        return {
            "count": len(exact),
            "minimum_distance": min(perceptual_distances) if perceptual_distances else None,
        }

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
