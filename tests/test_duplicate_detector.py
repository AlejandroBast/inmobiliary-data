from io import BytesIO
import unittest

from duplicate_detector import (
    Image,
    dhash_image,
    hash_distance,
    haversine_meters,
    normalize_text,
    score_publications,
)


class DuplicateDetectorTests(unittest.TestCase):
    def test_normalizes_colombian_address_variants(self):
        self.assertEqual(normalize_text("Carrera 24 # 18-40"), normalize_text("Cra. 24 No. 18-40"))

    def test_haversine_same_point(self):
        self.assertAlmostEqual(haversine_meters(1.2136, -77.2811, 1.2136, -77.2811), 0, places=3)

    def test_coordinates_do_not_confirm_by_themselves(self):
        first = {"latitud": 1.2136, "longitud": -77.2811, "tipo_inmueble": "Apartamento"}
        second = {"latitud": 1.2136, "longitud": -77.2811, "tipo_inmueble": "Apartamento"}
        score, _, _ = score_publications(first, second)
        self.assertLess(score, 60)

    def test_price_difference_is_not_a_penalty(self):
        base = {"direccion": "Calle 10 # 20-30", "m2": 80, "habitaciones": 3,
                "banios": 2, "tipo_inmueble": "Casa"}
        first = dict(base, precio=200_000_000)
        second = dict(base, precio=350_000_000)
        score, reasons, _ = score_publications(first, second, {"count": 1, "minimum_distance": 2})
        self.assertGreaterEqual(score, 80)
        self.assertFalse(any(reason["signal"] == "price" for reason in reasons))

    def test_single_image_without_location_remains_reviewable(self):
        first = {"m2": 80, "habitaciones": 3, "banios": 2, "tipo_inmueble": "Casa"}
        second = dict(first)
        score, reasons, _ = score_publications(first, second, {"count": 1, "minimum_distance": 2})
        self.assertGreaterEqual(score, 60)
        strong_location = any(reason["signal"] in {"same_address", "near_coordinates"} for reason in reasons)
        self.assertFalse(strong_location)

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
