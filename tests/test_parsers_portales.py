"""Pruebas de los extractores puros de cada portal.

Son las funciones que se rompen cuando el portal cambia su HTML, y hasta ahora
no tenian ninguna red de seguridad. No necesitan Playwright ni base de datos.
"""

import inmobiliary.scrapers.amorel as amorel
import inmobiliary.scrapers.ciencuadras as ciencuadras
import inmobiliary.scrapers.facebook as facebook
import inmobiliary.scrapers.fincaraiz as fincaraiz
import inmobiliary.scrapers.metrocuadrado as metrocuadrado


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


def test_fincaraiz_ubicacion_estructurada_prefiere_location_main():
    # location_main es la ubicacion propia de la ficha; neighbourhood es una
    # lista de barrios cercanos cuyo [0] puede no ser el de la publicacion.
    html = (
        '<script id="__NEXT_DATA__">'
        '{"props":{"pageProps":{"data":{'
        '"locations":{'
        '"location_main":{"name":"Torres del cielo 2","location_type":"neighbourhood"},'
        '"neighbourhood":[{"name":"Villa angela"},{"name":"Maria paz"}]},'
        '"address":"Torres del Cielo 2, Calle 28, Pasto, Nariño"}}}}'
        "</script>"
    )
    barrio, address = fincaraiz.extract_structured_location(html)
    assert barrio == "Torres del cielo 2"
    assert address == "Torres del Cielo 2, Calle 28, Pasto, Nariño"


def test_fincaraiz_acepta_fotos_del_cdn_nuevo_de_cloudfront():
    # Confirmado con evidencia real (publicacion 3227, 2026-07-28): Fincaraiz
    # esta migrando fotos a este CDN, y el filtro viejo (solo /repo/img/) las
    # descartaba todas, dejando la publicacion sin ninguna imagen.
    items = [
        {
            "url": (
                "https://d3s5pkt10pk3ga.cloudfront.net/resizedImages/742x400/site/"
                "fincaraiz_service/media/listing/f699e06f-db4a-49ee-820c-304ce22aeabb/"
                "photos/f699e06f-db4a-49ee-820c-304ce22aeabb_1_True_b17882fa-79ae-4fe2-8ce0-dec4c3b736a6.jpg"
            ),
            "width": 742,
            "height": 400,
        },
        # Miniatura lateral de otra foto: resolucion chica, pero es una foto
        # real (photos/.../_2_...), no un icono de UI. No debe descartarse
        # por tamaño como si viniera del CDN viejo.
        {
            "url": (
                "https://d3s5pkt10pk3ga.cloudfront.net/resizedImages/1x210/site/"
                "fincaraiz_service/media/listing/f699e06f-db4a-49ee-820c-304ce22aeabb/"
                "photos/f699e06f-db4a-49ee-820c-304ce22aeabb_2_False_9136075a-580e-47e8-986f-d58bde6c1f7c.jpg"
            ),
            "width": 1,
            "height": 210,
        },
        {"url": "https://cdn1.infocasas.com.uy/web/CO.png", "width": 24, "height": 20},
    ]

    result = fincaraiz.normalize_image_urls(items)

    assert len(result) == 2
    assert all("cloudfront.net/resizedImages" in url for url in result)


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


def test_ciencuadras_pisos_exige_plural_para_no_confundir_con_ubicacion():
    # "5 piso"/"segundo piso" describen en que piso queda la unidad, no
    # cuantos pisos tiene el inmueble.
    assert ciencuadras.extract_pisos("5 piso sin ascensor") is None
    assert ciencuadras.extract_pisos("ubicado en el segundo piso del Edificio") is None


def test_ciencuadras_pisos_acepta_plural_en_digitos_y_en_palabras():
    assert ciencuadras.extract_pisos("Casa de 3 pisos con un total de 10 habitaciones") == 3
    assert ciencuadras.extract_pisos("Espectacular casa de 180 mt2, de tres pisos") == 3
    assert ciencuadras.extract_pisos("Venta de casa de dos pisos independientes") == 2


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


def test_metrocuadrado_estrato_usa_la_clave_stratum_no_estrato():
    # El JSON embebido del sitio usa "stratum"; "estrato" nunca aparece como
    # clave real y antes dejaba este campo en NULL el 100% de las veces.
    source = '{"stratum":"4","estrato":"9"}'
    assert metrocuadrado.parse_int(
        metrocuadrado.regex_value(source, r'"stratum"\s*:\s*"?(\d+)"?')
    ) == 4


def test_metrocuadrado_administracion_desde_adminprice():
    source = '{"adminPrice":250000}'
    admin = metrocuadrado.parse_int(
        metrocuadrado.regex_value(source, r'"adminPrice"\s*:\s*(\d+)')
    ) or None
    assert admin == 250000

    source_null = '{"adminPrice":null}'
    admin_null = metrocuadrado.parse_int(
        metrocuadrado.regex_value(source_null, r'"adminPrice"\s*:\s*(\d+)')
    ) or None
    assert admin_null is None


def test_metrocuadrado_antiguedad_prefiere_builttime():
    source = '{"builtTime":"Entre 0 y 5 anos"}'
    assert metrocuadrado.regex_value(source, r'"builtTime"\s*:\s*"([^"]+)"') == "Entre 0 y 5 anos"


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


def test_amorel_extrae_area_construida_por_separado_del_area_de_lote():
    # Antes m2_construido quedaba siempre en None: nadie la intentaba extraer
    # aunque el aviso la distinga explicitamente del area de lote/terreno.
    assert amorel.extract_built_area("AREA CONSTRUIDA: 200 METROS CUADRADOS") == 200.0
    assert amorel.extract_built_area("80 m2 construidos") == 80.0
    assert amorel.extract_built_area("3 HABITACIONES, BAÑO, COMEDOR") is None


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


# Texto real de una publicacion guardada en la base: clean_text colapsa los
# saltos de linea, asi que la pagina entera llega como UNA sola linea.
BLOB_FACEBOOK_UNA_SOLA_LINEA = (
    "Se vende casa esquinera en barrio San Miguel $ 580 000 000 Inmuebles "
    "Publicidad Revista Semana NIVEA Iqlick.co. Ubicacion de la vivienda Pasto "
    "La ubicacion es aproximada Descripcion Se vende hermosa casa en barrio San "
    "Miguel 5 alcobas 3 banos sala comedor patio de ropas garaje doble Ver menos"
)


def test_facebook_extrae_la_ciudad_del_rotulo_y_no_la_pagina_entera():
    # Antes devolvia el blob completo: era "la primera linea que diga Pasto" y
    # el blob es una sola linea. Quedo guardado asi en la base.
    assert facebook.extract_location(BLOB_FACEBOOK_UNA_SOLA_LINEA) == "Pasto"


def test_facebook_no_toma_por_ciudad_un_texto_larguisimo():
    blob_sin_rotulo = "Vendo casa en el norte de Pasto con patio, garaje doble y tres banos amplios"
    assert facebook.extract_location(blob_sin_rotulo) is None
    assert facebook.extract_declared_city(blob_sin_rotulo) is None


def test_facebook_extrae_ubicacion_declarada_de_otra_ciudad():
    # Con la version vieja esto daba None (solo sabia reconocer "Pasto"), y sin
    # ciudad declarada el aviso se colaba.
    texto = "Apartamento en venta $ 300 000 000 Ubicacion de la vivienda Cali, Valle del Cauca Descripcion Lindo apto"
    assert facebook.extract_location(texto) == "Cali, Valle del Cauca"


def test_facebook_rechaza_ciudad_declarada_que_no_es_pasto():
    # Cali no esta en OUT_OF_CITY_KEYWORDS: antes pasaba el filtro y se guardaba
    # con ciudad='Pasto'.
    assert facebook.is_explicitly_out_of_city(
        "Casa en venta", "Hermosa casa", location_text="Cali, Valle del Cauca"
    ) is True
    assert facebook.is_explicitly_out_of_city(
        "Casa en venta", "Hermosa casa", location_text="Cartagena, Bolivar"
    ) is True


def test_facebook_acepta_pasto_y_sus_corregimientos():
    assert facebook.is_explicitly_out_of_city(
        "Casa en venta", "Hermosa casa", location_text="Pasto, Narino"
    ) is False
    # Algunos avisos declaran el corregimiento en vez de la ciudad.
    assert facebook.is_pasto_declared_city("CATAMBUCO") is True
    assert facebook.is_pasto_declared_city("CALI") is False


def test_facebook_ubicacion_contaminada_no_decide_el_municipio():
    # Si el campo vino con basura, se ignora y decide el texto libre, en vez de
    # rechazar un aviso valido de Pasto.
    assert facebook.is_explicitly_out_of_city(
        "Casa en venta en Pasto", "Barrio San Miguel", location_text=BLOB_FACEBOOK_UNA_SOLA_LINEA
    ) is False


def test_facebook_ciudad_sale_de_la_ubicacion_declarada():
    # Antes devolvia "Pasto" en las dos ramas del if, o sea siempre.
    assert facebook.extract_city("Casa", "texto", location_text="Cali, Valle del Cauca") == "Cali"
    assert facebook.extract_city("Casa", "texto", location_text="Pasto, Narino") == "Pasto"
    assert facebook.extract_city("Casa en Pasto", "texto") == "Pasto"


def test_facebook_rechaza_municipios_por_contexto():
    # Medellin y Bogota no estan en OUT_OF_CITY_KEYWORDS: los cubre el detector
    # compartido, que exige contexto ("casa en X", "municipio de X").
    assert facebook.is_explicitly_out_of_city("Casa en venta en Medellin", "") is True
    assert facebook.is_explicitly_out_of_city("Casa en venta en Ipiales", "") is True
    assert facebook.is_explicitly_out_of_city("Casa en venta en Pasto", "") is False


def test_facebook_no_confunde_el_adjetivo_bello_con_el_municipio():
    # "Bello" es municipio de Antioquia Y el adjetivo de "bello apartamento".
    # Buscar el nombre suelto omitia practicamente todos los avisos.
    assert facebook.is_explicitly_out_of_city("Casa en venta", "Vendo bello apartamento en Pasto") is False
    assert facebook.is_explicitly_out_of_city("Bella casa en venta", "Muy bello acabado, bella vista") is False
    assert facebook.is_explicitly_out_of_city("Casa en venta", "Hermosa casa en bello sector") is False


# Recorte del JSON embebido tal como viene en el HTML real de Marketplace.
HTML_GEOCODE_FACEBOOK = (
    '<script>{"listing":{"location":{"latitude":1.2167358398438,'
    '"longitude":-77.283325195312,'
    '"reverse_geocode_detailed":{"city":"Pasto","state":"","postal_code":"520002"},'
    '"reverse_geocode":{"city":"Pasto","state":"",'
    '"city_page":{"display_name":"Pasto","id":"108037152563666"}}}}}</script>'
)


def test_facebook_extrae_ciudad_y_coordenadas_de_la_geocodificacion():
    campos = facebook.extract_embedded_listing_fields(HTML_GEOCODE_FACEBOOK)

    assert campos["city"] == "Pasto"
    # Antes se guardaban siempre en NULL, sin que el detector de duplicados
    # pudiera comparar por distancia.
    assert campos["latitude"] == 1.2167358398438
    assert campos["longitude"] == -77.283325195312


def test_facebook_geocodificacion_de_otra_ciudad_descarta_el_aviso():
    html = HTML_GEOCODE_FACEBOOK.replace('"city":"Pasto"', '"city":"Bogot\\u00e1"')
    campos = facebook.extract_embedded_listing_fields(html)

    assert facebook.is_explicitly_out_of_city(
        "Apartamento en venta", "Lindo apto", location_text=campos["city"]
    ) is True


def test_facebook_sin_geocodificacion_no_revienta():
    campos = facebook.extract_embedded_listing_fields("<html><body>nada</body></html>")

    assert campos["city"] is None
    assert campos["latitude"] is None
    assert campos["longitude"] is None


def test_facebook_reconoce_el_encabezado_de_resultados_fuera_de_la_busqueda():
    # Texto exacto que muestra Marketplace cuando se agotan los avisos de la
    # ciudad y empieza a rellenar con otras.
    assert facebook.is_out_of_scope_heading("Resultados relacionados fuera de tu búsqueda") is True
    # Sin acentos y en otra capitalizacion tiene que dar igual.
    assert facebook.is_out_of_scope_heading("RESULTADOS RELACIONADOS FUERA DE TU BUSQUEDA") is True
    assert facebook.is_out_of_scope_heading("Related results outside your search") is True


def test_facebook_no_confunde_otros_textos_con_el_encabezado():
    assert facebook.is_out_of_scope_heading("Resultados de la búsqueda") is False
    assert facebook.is_out_of_scope_heading("Filtros") is False
    assert facebook.is_out_of_scope_heading("") is False
    assert facebook.is_out_of_scope_heading(None) is False


def test_facebook_ignora_un_contenedor_que_envuelve_media_pagina():
    # El textContent de un contenedor grande tambien "contiene" el encabezado. Si
    # se lo tomara por separador, los resultados buenos quedarian del lado
    # equivocado y no se recolectaria nada.
    contenedor = (
        "Se vende Lote Pasto Se vende casa en el barrio San Ignacio Pasto Vendo casa "
        "campestre Pasto Resultados relacionados fuera de tu búsqueda Apartamento en "
        "Bogotá Casa en Fusagasugá y muchas mas publicaciones de relleno"
    )
    assert facebook.is_out_of_scope_heading(contenedor) is False


def test_facebook_descarta_tarjeta_de_otro_departamento():
    # Asi se ve una tarjeta del listado: precio, titulo y ubicacion por linea.
    tarjeta = "$ 320.000.000\nVendo casa de 2 pisos\nFusagasuga, Cundinamarca"
    assert facebook.card_city_is_outside_pasto(tarjeta) is True
    assert facebook.card_city_is_outside_pasto("$ 1\nApto\nBogota, D.C.") is True


def test_facebook_conserva_tarjeta_de_pasto():
    tarjeta = "$ 580.000.000\nCasa esquinera barrio San Miguel\nPasto, Narino"
    assert facebook.card_city_is_outside_pasto(tarjeta) is False


def test_facebook_descarta_otro_municipio_de_narino():
    tarjeta = "$ 90.000.000\nCasa campestre\nIpiales, Narino"
    assert facebook.card_city_is_outside_pasto(tarjeta) is True


def test_facebook_tarjeta_sin_ubicacion_reconocible_se_conserva():
    # Si no se puede decidir, la publicacion se abre igual: el filtro de detalle
    # tiene el texto completo. Un cambio de maquetado nunca debe perder avisos.
    assert facebook.card_city_is_outside_pasto("$ 100\nCasa linda, muy amplia") is False
    assert facebook.card_city_is_outside_pasto("Pasto") is False
    assert facebook.card_city_is_outside_pasto("") is False
    assert facebook.card_city_is_outside_pasto(None) is False


def test_facebook_extrae_antiguedad_de_frases_comunes():
    # Antes este campo quedaba siempre en None: Facebook es el unico scraper
    # que nunca lo intentaba extraer.
    assert facebook.extract_antiguedad("Apartamento para estrenar en Chapal") == "Para Estrenar"
    assert facebook.extract_antiguedad("Apartamento en obra gris, ubicado en Barrio Alta") == "Obra Gris"
    assert facebook.extract_antiguedad("Casa amplia con jardin y garaje") is None
