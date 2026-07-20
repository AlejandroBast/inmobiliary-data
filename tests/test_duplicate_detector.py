from io import BytesIO
import unittest

from inmobiliary.detectors.duplicates import (
    Image,
    dhash_image,
    hash_distance,
    haversine_meters,
    normalize_text,
    score_publications,
    sha256_stream,
)


class DuplicateDetectorTests(unittest.TestCase):
    def test_sha256_requires_identical_file_content(self):
        first = BytesIO(b"same-image-content")
        second = BytesIO(b"same-image-content")
        changed = BytesIO(b"same-image-content!")
        self.assertEqual(sha256_stream(first), sha256_stream(second))
        self.assertNotEqual(
            sha256_stream(BytesIO(b"same-image-content")),
            sha256_stream(changed),
        )

    def test_normalizes_colombian_address_variants(self):
        self.assertEqual(normalize_text("Carrera 24 # 18-40"), normalize_text("Cra. 24 No. 18-40"))

    def test_haversine_same_point(self):
        self.assertAlmostEqual(haversine_meters(1.2136, -77.2811, 1.2136, -77.2811), 0, places=3)

    def test_coordinates_do_not_confirm_by_themselves(self):
        first = {"latitud": 1.2136, "longitud": -77.2811, "tipo_inmueble": "Apartamento"}
        second = {"latitud": 1.2136, "longitud": -77.2811, "tipo_inmueble": "Apartamento"}
        score, _, _ = score_publications(first, second)
        self.assertLess(score, 60)

    def test_price_difference_does_not_hide_a_strong_duplicate(self):
        base = {"direccion": "Calle 10 # 20-30", "m2": 80, "habitaciones": 3,
                "banios": 2, "tipo_inmueble": "Casa"}
        first = dict(base, precio=200_000_000)
        second = dict(base, precio=350_000_000)
        score, reasons, _ = score_publications(first, second, {"count": 1, "minimum_distance": 2})
        self.assertGreaterEqual(score, 80)
        self.assertFalse(any(reason["signal"] == "different_price" for reason in reasons))

    def test_single_image_without_location_remains_reviewable(self):
        first = {"m2": 80, "habitaciones": 3, "banios": 2, "tipo_inmueble": "Casa"}
        second = dict(first)
        score, reasons, _ = score_publications(first, second, {"count": 1, "minimum_distance": 2})
        self.assertGreaterEqual(score, 60)
        strong_location = any(reason["signal"] in {"same_address", "near_coordinates"} for reason in reasons)
        self.assertFalse(strong_location)

    def test_uses_extended_property_fields(self):
        base = {
            "ciudad": "Pasto", "barrio": "Palermo", "tipo_inmueble": "Apartamento",
            "ph": "Edificio Mirador", "estrato": 4, "m2": 82, "m2_construido": 80,
            "habitaciones": 3, "banios": 2, "parqueadero": 1, "pisos": 1,
            "administracion": 250_000, "precio": 320_000_000,
            "antiguedad": "5 a 10 años",
            "descripcion": "Apartamento iluminado con balcon y vista panoramica.",
        }
        score, reasons, _ = score_publications(base, dict(base))
        signals = {reason["signal"] for reason in reasons}
        self.assertGreaterEqual(score, 50)
        self.assertTrue({
            "same_city", "same_neighborhood", "same_property_type", "same_building",
            "same_stratum", "similar_area", "similar_built_area", "same_bedrooms",
            "same_bathrooms", "same_parking", "same_floors", "similar_price",
            "similar_administration", "same_age", "very_similar_description",
        }.issubset(signals))

    def test_hard_conflicts_reduce_false_positives(self):
        first = {
            "ciudad": "Pasto", "tipo_inmueble": "Casa", "m2": 80,
            "m2_construido": 75, "habitaciones": 3, "banios": 2,
            "latitud": 1.2136, "longitud": -77.2811,
        }
        second = {
            "ciudad": "Medellin", "tipo_inmueble": "Apartamento", "m2": 180,
            "m2_construido": 170, "habitaciones": 5, "banios": 4,
            "latitud": 6.2442, "longitud": -75.5812,
        }
        score, reasons, _ = score_publications(first, second, {"count": 1, "minimum_distance": 2})
        signals = {reason["signal"] for reason in reasons}
        self.assertLess(score, 60)
        self.assertIn("different_city", signals)
        self.assertIn("different_property_type", signals)
        self.assertIn("distant_coordinates", signals)

    @unittest.skipIf(Image is None, "Pillow no esta instalado")
    def test_dhash_survives_resize_and_jpeg_compression(self):
        image = Image.new("RGB", (400, 300), "white")
        for x in range(50, 350):
            for y in range(60, 240):
                if (x // 30 + y // 30) % 2:
                    image.putpixel((x, y), (25, 80, 160))
        compressed_bytes = BytesIO()
        image.resize((280, 210)).save(compressed_bytes, format="JPEG", quality=60)
        compressed_bytes.seek(0)
        with Image.open(compressed_bytes) as compressed:
            first = dhash_image(image)
            second = dhash_image(compressed)
        self.assertLessEqual(hash_distance(first, second), 8)


if __name__ == "__main__":
    unittest.main()
