import pytest

from inmobiliary.detectors import ph


@pytest.fixture
def catalogo_ph(tmp_path, monkeypatch):
    catalog_file = tmp_path / "pasto_ph.tsv"
    catalog_file.write_text(
        "# comentario, se ignora\n\nTorres de Aquine\nConjunto Los Rosales\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ph, "CATALOG_PATH", catalog_file)
    ph.load_ph_catalog.cache_clear()
    yield
    ph.load_ph_catalog.cache_clear()


def test_reconoce_nombre_de_catalogo_sin_palabras_clave_de_ph(catalogo_ph):
    # Sin "PH", "conjunto" ni "edificio" en el texto: solo el nombre catalogado.
    assert ph.detect_ph("Apartamento en Torres de Aquine, Pasto") == "Torres de Aquine"


def test_catalogo_tiene_prioridad_sobre_deteccion_generica(catalogo_ph):
    assert ph.detect_ph("Bonito apto en Conjunto Los Rosales, cuenta con piscina") == "Conjunto Los Rosales"


def test_negacion_explicita_gana_incluso_con_nombre_de_catalogo(catalogo_ph):
    assert ph.detect_ph("Casa cerca a Torres de Aquine, sin PH") is None


def test_nombre_no_catalogado_no_se_registra(catalogo_ph):
    # "Conjunto Cerrado Las Palmeras" no esta en el catalogo de prueba: sin
    # nombre confirmado, la publicacion queda sin PH en vez de guardar el
    # texto libre extraido por regex.
    assert ph.detect_ph("Apartamento en Conjunto Cerrado Las Palmeras, con administracion incluida") is None


def test_evidencia_generica_sin_nombre_catalogado_no_se_registra(catalogo_ph):
    # Antes esto devolvia el marcador generico "Si"; ahora, sin un nombre del
    # catalogo, no hay suficiente informacion para asignar un PH.
    assert ph.detect_ph("Casa campestre, cuenta con propiedad horizontal") is None


def test_complex_name_no_catalogado_no_se_registra(catalogo_ph):
    # complex_name (lo que extraiga el scraper, p. ej. Amorel) ya no se
    # devuelve tal cual: solo cuenta si el catalogo lo reconoce.
    assert ph.detect_ph("Apartamento amplio y comodo", complex_name="Conjunto Los Alamos") is None


def test_complex_name_catalogado_se_normaliza_al_nombre_del_catalogo(catalogo_ph):
    assert ph.detect_ph("Apartamento amplio", complex_name="conjunto los rosales") == "Conjunto Los Rosales"


def test_sin_ninguna_senal_devuelve_none(catalogo_ph):
    assert ph.detect_ph("Casa independiente en el centro, sin PH") is None
    assert ph.detect_ph("Lote esquinero en via Catambuco") is None
