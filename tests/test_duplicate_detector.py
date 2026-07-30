from io import BytesIO
import unittest

from inmobiliary.detectors.duplicates import (
    Image,
    dhash_image,
    hash_distance,
    haversine_meters,
    is_street_level_address,
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

    def test_una_brecha_grande_de_precio_separa_los_avisos(self):
        # Politica nueva: el precio es, con las imagenes, la senal principal. Un
        # 75% de brecha son dos inmuebles distintos aunque compartan direccion y
        # foto (un vendedor suele reusar fotos del edificio entre unidades).
        # Antes el precio nunca restaba y este par quedaba en 84.
        base = {"direccion": "Calle 10 # 20-30", "m2": 80, "habitaciones": 3,
                "banios": 2, "tipo_inmueble": "Casa"}
        first = dict(base, precio=200_000_000)
        second = dict(base, precio=350_000_000)
        score, reasons, _ = score_publications(first, second, {"count": 1, "minimum_distance": 2})
        signals = {reason["signal"] for reason in reasons}

        self.assertIn("different_price", signals)
        self.assertLess(score, 60)

    def test_una_diferencia_chica_de_precio_no_estorba(self):
        # El mismo inmueble reSubido por otro vendedor suele moverse poco.
        base = {"direccion": "Calle 10 # 20-30", "m2": 80, "habitaciones": 3,
                "banios": 2, "tipo_inmueble": "Casa"}
        first = dict(base, precio=200_000_000)
        second = dict(base, precio=210_000_000)
        score, reasons, _ = score_publications(first, second, {"count": 1, "minimum_distance": 2})
        signals = {reason["signal"] for reason in reasons}

        self.assertIn("very_similar_price", signals)
        self.assertNotIn("different_price", signals)
        self.assertGreaterEqual(score, 80)

    def test_el_precio_identico_pesa_mas_que_uno_parecido(self):
        base = {"tipo_inmueble": "Casa", "ciudad": "Pasto"}
        igual, _, _ = score_publications(
            dict(base, precio=280_000_000), dict(base, precio=280_000_000))
        parecido, _, _ = score_publications(
            dict(base, precio=280_000_000), dict(base, precio=250_000_000))

        self.assertGreater(igual, parecido)

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
            "same_bathrooms", "same_parking", "same_floors", "same_price",
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


class DireccionNivelCalle(unittest.TestCase):
    def test_reconoce_direcciones_de_calle(self):
        self.assertTrue(is_street_level_address(normalize_text("Carrera 5 # 12-34")))
        self.assertTrue(is_street_level_address(normalize_text("Calle 20 con Avenida Panamericana")))
        self.assertTrue(is_street_level_address(normalize_text("Manzana 3 lote 7")))

    def test_barrio_y_ciudad_no_son_direccion(self):
        # Asi arma la direccion el scraper de Facebook: "<barrio>, Pasto, Narino".
        self.assertFalse(is_street_level_address(normalize_text("La Colina, Pasto, Narino")))
        self.assertFalse(is_street_level_address(normalize_text("Pasto, Narino")))

    def test_misma_zona_no_puntua_como_misma_direccion(self):
        # Dos apartamentos distintos del mismo barrio traen exactamente la misma
        # cadena. Sumarle 20 puntos alcanzaba para cruzar el umbral de revision
        # sin ninguna evidencia real.
        base = {
            "direccion": "La Colina, Pasto, Narino", "ciudad": "Pasto",
            "barrio": "La Colina", "tipo_inmueble": "Apartamento",
        }
        otro = dict(base)
        score, reasons, _ = score_publications(base, otro)
        signals = {reason["signal"] for reason in reasons}

        self.assertIn("same_area_not_address", signals)
        self.assertNotIn("same_address", signals)
        self.assertLess(score, 60)

    def test_direccion_de_calle_identica_si_puntua(self):
        base = {
            "direccion": "Carrera 5 # 12-34", "ciudad": "Pasto",
            "tipo_inmueble": "Apartamento",
        }
        score, reasons, _ = score_publications(base, dict(base))
        signals = {reason["signal"] for reason in reasons}

        self.assertIn("same_address", signals)
        self.assertNotIn("same_area_not_address", signals)


class PuntajeSimetrico(unittest.TestCase):
    def test_el_puntaje_no_depende_del_orden(self):
        # El detector puntua cada par dos veces (una por publicacion) y guarda el
        # ultimo resultado. Con SequenceMatcher sin ordenar, un par real quedaba
        # con 70 o con 74 segun cual se procesara primero.
        a = {
            "ciudad": "Pasto", "tipo_inmueble": "Apartamento", "barrio": "Valle De Atriz",
            "m2": 110, "habitaciones": 3, "banios": 2, "precio": 450000000,
            "descripcion": "SE VENDE APTO 110 m2 Pasto Norte Valle de Atriz 3 habitaciones 2 banos",
        }
        b = {
            "ciudad": "Pasto", "tipo_inmueble": "Apartamento", "barrio": "Las Ferias",
            "m2": 100, "habitaciones": 3, "banios": 2, "precio": 480000000,
            "descripcion": "SE VENDE APARTAMENTO 100 m2 Pasto Norte Valle de ATRIZ 3 habitaciones banos",
        }
        imagenes = {"count": 0, "near_count": 5, "minimum_distance": 0}

        ida, _, _ = score_publications(a, b, imagenes)
        vuelta, _, _ = score_publications(b, a, imagenes)

        self.assertEqual(ida, vuelta)

    def test_similitud_de_texto_es_simetrica(self):
        from inmobiliary.detectors.duplicates import text_similarity

        primero = "se vende apto 110 m2 pasto norte valle de atriz 3 habitaciones"
        segundo = "se vende apartamento 100 m2 pasto norte valle de atriz 3 habitaciones"

        self.assertEqual(text_similarity(primero, segundo), text_similarity(segundo, primero))


class ImagenesRecomprimidas(unittest.TestCase):
    def test_misma_foto_resubida_cuenta_como_evidencia(self):
        # Facebook recomprime la foto al reSubirla, asi que el SHA-256 cambia. Con
        # solo hash exacto, un duplicado real quedaba sin ninguna senal visual.
        # Caso tomado de un par real: mismo lote publicado dos veces, mismo precio
        # y 7 fotos perceptualmente identicas.
        base = {
            "ciudad": "Pasto", "tipo_inmueble": "Lote", "precio": 280000000,
            "ph": "Conjunto Cerrado", "descripcion": "Amplio lote en conjunto cerrado",
        }
        score, reasons, _ = score_publications(
            base, dict(base), {"count": 0, "near_count": 7, "minimum_distance": 0}
        )
        signals = {reason["signal"] for reason in reasons}

        self.assertIn("same_images_recompressed", signals)
        self.assertNotIn("identical_images", signals)
        self.assertGreaterEqual(score, 60)

    def test_las_fotos_solas_no_alcanzan_para_revisar(self):
        # A proposito: la senal visual llega a 45 (35 exacto llega a 50) y siempre
        # necesita corroboracion. Una foto compartida entre dos avisos distintos
        # es comun, y sin este tope alcanzaba para marcarlos como duplicados.
        base = {"ciudad": "Pasto", "tipo_inmueble": "Lote"}
        score, _, _ = score_publications(
            base, dict(base), {"count": 0, "near_count": 7, "minimum_distance": 0}
        )
        self.assertLess(score, 60)

    def test_el_archivo_identico_sigue_valiendo_mas(self):
        base = {"ciudad": "Pasto", "tipo_inmueble": "Lote"}
        exacto, _, _ = score_publications(base, dict(base), {"count": 1, "near_count": 0, "minimum_distance": 0})
        parecido, _, _ = score_publications(base, dict(base), {"count": 0, "near_count": 1, "minimum_distance": 3})

        self.assertGreater(exacto, parecido)

    def test_sin_imagenes_no_hay_senal_visual(self):
        base = {"ciudad": "Pasto", "tipo_inmueble": "Lote"}
        _, reasons, _ = score_publications(base, dict(base), {"count": 0, "near_count": 0, "minimum_distance": 21})
        signals = {reason["signal"] for reason in reasons}

        self.assertNotIn("identical_images", signals)
        self.assertNotIn("same_images_recompressed", signals)


if __name__ == "__main__":
    unittest.main()
