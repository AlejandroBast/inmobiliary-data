from inmobiliary.detectors.location import resolve_pasto_location


def test_aliases_seguros():
    assert resolve_pasto_location("Toro bajo").value == "Torobajo"
    assert resolve_pasto_location("Villa Flor 2").value == "Villaflor II"
    assert resolve_pasto_location("Violetas Ii").value == "Las Violetas II"


def test_corregimiento_solo_por_nombre_explicito():
    assert resolve_pasto_location("Vereda La Laguna").value == "La Laguna"
    assert resolve_pasto_location("San Luis").value is None
    assert resolve_pasto_location("San Fernando Alto").value is None


def test_descripcion_y_texto_contaminado():
    result = resolve_pasto_location(
        "Via Que Va A Jongovito 8 De Frente X 16 De Fondo",
        description="Lote en el corregimiento de Gualmatán frente al pueblo por la vía a Jongovito",
    )
    assert result.value == "Gualmatán"
    assert result.confidence >= 80


def test_ph_con_alias_tradicional_conocido_permite_recuperar_ubicacion():
    result = resolve_pasto_location("Conjunto Mirador De Aquine", ph="Conjunto Mirador De Aquine")
    assert result.value == "Aquine"


def test_barrio_oficial_directo_en_descripcion_aunque_haya_ph():
    result = resolve_pasto_location(
        "Condominio Agualongo II",
        description="Se vende apartamento en Condominio Agualongo II",
        ph="Condominio Agualongo II",
    )
    assert result.value == "Agualongo"


def test_fallback_tradicional_solo_despues_del_catalogo():
    assert resolve_pasto_location(
        "Mirador Torres de Aquine", description="Apartamento en Mirador Torres de Aquine"
    ).value == "Aquine"
    assert resolve_pasto_location(
        description="Apartamento a dos cuadras de Unicentro"
    ).value == "Unicentro"


def test_municipio_externo_prevalece():
    result = resolve_pasto_location("Arizona", city="Pasto", description="Casa en el municipio de Chachagüí")
    assert result.value is None
    assert result.outside_municipality == "Chachagui"
