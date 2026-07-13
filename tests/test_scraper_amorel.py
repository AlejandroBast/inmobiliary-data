import pytest

import scraper_amorel_pasto as amorel
from scraper_amorel_pasto import extract_barrio, extract_images, extract_price, is_plausible_barrio


def test_extract_price_does_not_treat_contact_phone_as_price():
    description = (
        "FSE 22108 VENDO CASA DE DOS APARTAMENTOS BARRIO NUEVO SOL "
        "INF. 3159937097"
    )

    assert extract_price(description) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("VALOR $ 165.000.000 INF. 3159937097", 165_000_000),
        ("Precio de venta: 280.000.000 Informes 3101234567", 280_000_000),
        ("Se vende casa en 350 millones. Celular 3159937097", 350_000_000),
        ("Inversion COP 420,000,000", 420_000_000),
    ],
)
def test_extract_price_requires_and_uses_a_money_signal(text, expected):
    assert extract_price(text) == expected


def test_extract_barrio_prefers_real_location_over_marketing_phrase():
    description = (
        "UBICACION: TORRE 2 PISO 2 RESERVAS DE ALTAMIRA. "
        "Un apartamento comodo, funcional e ideal para disfrutar en familia."
    )

    assert extract_barrio("Apartamento Reservas de Altamira", description) == "Altamira"
    assert not is_plausible_barrio("Familia")


def test_extract_images_prefers_full_image_over_thumbnail():
    parser = amorel.SimpleHTMLParser()
    parser.images = [
        {"src": "/clasificados/web/api/v1/anuncio/34176/thumb"},
        {"src": "/clasificados/web/api/v1/anuncio/34176/imagen"},
        {"src": "/clasificados/web/api/v1/anuncio/34177/imagen"},
    ]

    urls = extract_images(parser, "https://amorelpasto.com/detalle/1")

    assert len(urls) == 2
    assert all(url.endswith("/imagen") for url in urls)


def test_download_image_writes_to_publication_image_directory(monkeypatch, tmp_path):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return b"fake-jpeg"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(amorel, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    path = amorel.download_image("https://example.test/image", "FSE 21563", 1, 39)

    assert path == tmp_path / "evidencias" / "publicacion_39" / "imagenes" / "amorel_FSE_21563_01.jpg"
    assert path.read_bytes() == b"fake-jpeg"
