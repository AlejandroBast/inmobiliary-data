import pytest

from scrapers.core.normalizers import (
    calculate_precio_m2,
    detect_ph,
    extract_barrio,
    is_sale_listing,
    parse_area,
    parse_price,
    sale_status,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("precio 350 millones", 350_000_000),
        ("Vendo lote en Jamondino $180.000.000", 180_000_000),
        ("Valor de venta: $ 165.000.000", 165_000_000),
    ],
)
def test_parse_price_colombian_formats(text, expected):
    assert parse_price(text) == expected


def test_sale_detection_accepts_sale_and_rejects_rent_or_anticresis():
    assert is_sale_listing("Se vende casa en barrio Palermo Pasto")
    assert sale_status("Arriendo apartamento en conjunto cerrado") == (False, "no_venta")
    assert sale_status("Anticresis casa sector centro") == (False, "no_venta")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Se vende casa en barrio Palermo Pasto, 120 m2, precio 350 millones", "Palermo"),
        ("Vendo lote en Jamondino $180.000.000", "Jamondino"),
        ("Apartamento en conjunto residencial, barrio Morasurco", "Morasurco"),
        ("Anticresis casa sector centro", "Centro"),
    ],
)
def test_extract_barrio_from_common_listing_phrases(text, expected):
    assert extract_barrio(text) == expected


def test_detect_ph_keywords():
    assert detect_ph("Arriendo apartamento en conjunto cerrado") == "Conjunto Cerrado"
    assert detect_ph("Apartamento en conjunto residencial, barrio Morasurco") == "Conjunto Residencial"
    assert detect_ph("Casa independiente barrio Palermo") is None


def test_parse_area_and_calculate_precio_m2():
    text = "Se vende casa en barrio Palermo Pasto, 120 m2, precio 350 millones"
    assert parse_area(text) == 120
    assert calculate_precio_m2(parse_price(text), parse_area(text)) == pytest.approx(2_916_666.6667)
