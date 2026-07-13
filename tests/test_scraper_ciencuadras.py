import pytest

from scraper_ciencuadras import extract_ph


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "APARTAMENTO EN VENTA Conjunto: Bosques de La Colina III "
            "Torre 4 - Apto 105 Area: 56m2",
            "Conjunto Bosques de La Colina III",
        ),
        ("Apartamento en Edificio Mirador del Parque, piso 5", "Edificio Mirador del Parque"),
        ("Vivienda sometida a propiedad horizontal.", "Propiedad Horizontal"),
        ("Casa independiente en barrio Palermo", None),
    ],
)
def test_extract_ph_from_ciencuadras_description(description, expected):
    assert extract_ph(description) == expected
