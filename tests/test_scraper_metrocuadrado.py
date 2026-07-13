from scraper_metrocuadrado_pasto import extract_listing_links_from_html


def test_extracts_embedded_pasto_links_and_ignores_other_cities():
    html = """
    /inmueble/venta-lote-pasto-el-bordo/21605-M6293421?src_url=search
    https://www.metrocuadrado.com/inmueble/venta-casa-pasto-palermo/123-M1234567
    /inmueble/venta-apartamento-cali-centro/456-M7654321
    /inmueble/venta-lote-pasto-el-bordo/21605-M6293421
    """

    assert extract_listing_links_from_html(html) == [
        "https://www.metrocuadrado.com/inmueble/venta-lote-pasto-el-bordo/21605-M6293421",
        "https://www.metrocuadrado.com/inmueble/venta-casa-pasto-palermo/123-M1234567",
    ]
