import scraper_fincaraiz_pasto as fincaraiz


def test_title_barrio_has_priority_over_map_location(monkeypatch):
    monkeypatch.setattr(
        fincaraiz,
        "extract_structured_location",
        lambda _html: ("Co. achalay", "Co. achalay, Nariño"),
    )

    ciudad, barrio, direccion = fincaraiz.extract_location(
        lines=[],
        title="Apartamento en Venta en La aurora, Pasto",
        text="",
        html="map-data",
    )

    assert ciudad == "Pasto"
    assert barrio == "La aurora"
    assert direccion == "La aurora, Pasto, Nariño"


def test_map_location_is_ignored_when_title_has_no_barrio(monkeypatch):
    monkeypatch.setattr(
        fincaraiz,
        "extract_structured_location",
        lambda _html: ("Co. achalay", "Co. achalay, Nariño"),
    )
    _, barrio, direccion = fincaraiz.extract_location(
        lines=["Ubicación Principal", "La aurora, Pasto, Nariño"],
        title="Apartamento en Venta en Pasto",
        text="",
        html="map-data",
    )

    assert barrio is None
    assert direccion == "Pasto, Nariño"


def test_extracts_las_lunas_from_bold_title():
    _, barrio, direccion = fincaraiz.extract_location(
        lines=["Ubicación", "Luna et. i, Nariño"],
        title="Lote en Venta en Las lunas et. ii, Pasto",
        text="Luna et. i",
        html="map-data",
    )

    assert barrio == "Las lunas et. ii"
    assert direccion == "Las lunas et. ii, Pasto, Nariño"


def test_rejects_titles_from_other_cities():
    assert fincaraiz.is_pasto_title("Apartamento en Venta en La aurora, Pasto")
    assert fincaraiz.is_pasto_title("Casa campestre en Venta en Pasto")
    assert not fincaraiz.is_pasto_title(
        "BRASSIKA CLUB LIVING, Apartamentos en Venta en Santa ana, Palmira"
    )
    assert not fincaraiz.is_pasto_title("Apartamentos en Venta en Bello")
    assert not fincaraiz.is_pasto_title("Apartamentos en Venta en Apartadó")
