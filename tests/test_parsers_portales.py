"""Pruebas de los extractores puros de cada portal.

Son las funciones que se rompen cuando el portal cambia su HTML, y hasta ahora
no tenian ninguna red de seguridad. No necesitan Playwright ni base de datos.
"""

import scraper_amorel_pasto as amorel
import scraper_ciencuadras as ciencuadras
import scraper_facebook_marketplace as facebook
import scraper_fincaraiz_pasto as fincaraiz
import scraper_metrocuadrado_pasto as metrocuadrado


# ==========================================================
# FINCARAIZ
# ==========================================================

def test_fincaraiz_extrae_precio_con_separador_de_miles():
    assert fincaraiz.extract_precio("Precio $ 250.000.000 Area 100 m2") == 250_000_000


def test_fincaraiz_sin_precio_devuelve_none():
    assert fincaraiz.extract_precio("sin datos") is None
    assert fincaraiz.extract_precio("") is None
    assert fincaraiz.extract_precio(None) is None


def test_fincaraiz_lee_el_contador_de_resultados():
    assert fincaraiz.extract_total_results("Mostrando 1 - 20 de 1.234 resultados") == 1234
    assert fincaraiz.extract_result_window("Mostrando 1 - 20 de 1.234 resultados") == (1, 20, 1234)


def test_fincaraiz_separa_tipo_y_barrio_del_titulo():
    assert fincaraiz.extract_title_parts("Casa en Venta en San Fernando, Pasto") == ("Casa", "San Fernando")
    assert fincaraiz.extract_title_parts("Apartamento en venta en la colina, pasto") == ("Apartamento", "la colina")


def test_fincaraiz_titulo_vacio_no_revienta():
    assert fincaraiz.extract_title_parts(None) == (None, None)
    assert fincaraiz.extract_title_parts("") == (None, None)


def test_fincaraiz_parse_colombian_decimal_distingue_miles_de_decimales():
    assert fincaraiz.parse_colombian_decimal("1.104 m2") == 1104.0
    assert fincaraiz.parse_colombian_decimal("118.65 m2") == 118.65
    assert fincaraiz.parse_colombian_decimal("sin area") is None


# ==========================================================
# CIENCUADRAS
# ==========================================================

def test_ciencuadras_extrae_precio_por_etiqueta_y_por_simbolo():
    assert ciencuadras.extract_precio("Valor de compra: $ 180.000.000") == 180_000_000
    assert ciencuadras.extract_precio("$ 350.000.000") == 350_000_000


def test_ciencuadras_sin_precio_devuelve_none():
    assert ciencuadras.extract_precio("consultar precio") is None
    assert ciencuadras.extract_precio(None) is None


def test_ciencuadras_extrae_codigo_con_tilde():
    assert ciencuadras.extract_codigo("Código: CC-987") == "CC-987"
    assert ciencuadras.extract_codigo("sin codigo") is None


def test_ciencuadras_separa_tipo_y_barrio_del_titulo():
    assert ciencuadras.extract_title_parts("Casa en venta, El dorado") == ("Casa", "El dorado")


def test_ciencuadras_titulo_sin_coma_no_da_barrio():
    assert ciencuadras.extract_title_parts("Casa en venta") == (None, None)


def test_ciencuadras_lee_el_contador_de_resultados():
    assert ciencuadras.extract_total_results("de 456 resultados") == 456
    assert ciencuadras.extract_total_results("sin resultados aun") is None


# ==========================================================
# METROCUADRADO
# ==========================================================

def test_metrocuadrado_lee_el_contador_de_resultados():
    assert metrocuadrado.extract_total_results("1.234 resultados") == 1234


def test_metrocuadrado_saca_el_codigo_de_la_url():
    url = "https://www.metrocuadrado.com/inmueble/venta-casa-pasto/9876"
    assert metrocuadrado.extract_codigo(url, "") == "9876"


def test_metrocuadrado_detecta_el_tipo_en_el_titulo():
    assert metrocuadrado.extract_tipo("Casa en venta en Pasto", "") == "Casa"


# ==========================================================
# AMOREL
# ==========================================================

def test_amorel_extrae_precio():
    assert amorel.extract_price("Valor $ 320.000.000") == 320_000_000
    assert amorel.parse_money_digits("$ 320.000.000") == 320_000_000


def test_amorel_acepta_venta_y_rechaza_arriendo():
    aceptada, motivo = amorel.is_sale_listing("SE VENDE CASA", "casas venta", "")
    assert aceptada is True and motivo is None

    aceptada, motivo = amorel.is_sale_listing("SE ARRIENDA APTO", "casas venta", "")
    assert aceptada is False and motivo


def test_amorel_detecta_tipo_de_inmueble():
    assert amorel.extract_property_type("VENDO APARTAMENTO", "", "", None) == "Apartamento"


def test_amorel_extrae_area_con_superindice():
    # normalize_text convierte M² en M2; sin eso el area se perdia en silencio.
    assert amorel.extract_area("AREA 86 M2") == 86.0
    assert amorel.extract_area("AREA 86 M²") == 86.0


def test_amorel_extrae_habitaciones():
    assert amorel.extract_habitaciones("3 HABITACIONES") == 3


def test_amorel_saca_el_id_de_la_url():
    url = "https://amorelpasto.com/clasificados/web/app.php/publicacion/4521"
    assert amorel.extract_publication_id(url) == "4521"


# ==========================================================
# FACEBOOK MARKETPLACE
# ==========================================================

def test_facebook_saca_el_id_del_item():
    assert facebook.extract_marketplace_id("https://www.facebook.com/marketplace/item/123456789/") == "123456789"
    assert facebook.extract_marketplace_id("https://www.facebook.com/otra/cosa") is None


def test_facebook_normaliza_el_link_quitando_parametros():
    assert facebook.normalize_marketplace_link("/marketplace/item/999/?ref=x") == (
        "https://www.facebook.com/marketplace/item/999/"
    )


def test_facebook_link_que_no_es_de_marketplace_se_descarta():
    assert facebook.normalize_marketplace_link("/groups/123") is None
    assert facebook.normalize_marketplace_link(None) is None


def test_facebook_extrae_precio_con_comas():
    assert facebook.extract_price("$250,000,000") == 250_000_000


def test_facebook_acepta_venta_y_rechaza_arriendo():
    aceptada, motivo = facebook.is_sale_listing("Casa en venta", "")
    assert aceptada is True and motivo is None

    aceptada, motivo = facebook.is_sale_listing("Casa en arriendo", "")
    assert aceptada is False and motivo


def test_facebook_detecta_tipo_de_inmueble():
    assert facebook.extract_property_type("Casa grande", "") == "Casa"
