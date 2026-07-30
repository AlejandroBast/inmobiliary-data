import inmobiliary.scrapers.facebook as fb


def test_incremental_usa_un_solo_listado_sin_buckets_de_precio():
    completo = fb.build_search_urls(incremental=False)
    incremental = fb.build_search_urls(incremental=True)

    assert len(incremental) < len(completo)
    assert not any("minPrice" in url or "maxPrice" in url for url in incremental)


def test_no_se_ordena_por_mas_reciente_por_defecto():
    # Ordenar por mas reciente hace que Marketplace deje de mostrar el encabezado
    # "Resultados relacionados fuera de tu busqueda", que es el corte del scroll:
    # sin el, la corrida se iba a miles de publicaciones.
    for url in fb.build_search_urls(incremental=False) + fb.build_search_urls(incremental=True):
        assert "sortBy" not in url


def test_orden_por_mas_reciente_es_opcional(monkeypatch):
    monkeypatch.setattr(fb, "SORT_BY_NEWEST", True)

    for url in fb.build_search_urls(incremental=True):
        assert "sortBy=creation_time_descend" in url


def test_barrido_completo_conserva_los_buckets_de_precio():
    completo = fb.build_search_urls(incremental=False)

    assert len(completo) == len(fb.DEFAULT_PRICE_BUCKETS) + 1
    assert any("minPrice" in url for url in completo)


def test_usa_el_listado_de_inmuebles_de_pasto():
    # URL copiada del navegador con los filtros puestos desde la UI.
    for url in fb.build_search_urls(incremental=False) + fb.build_search_urls(incremental=True):
        assert f"/marketplace/{fb.PASTO_LOCATION_ID}/search" in url
        assert "query=Inmuebles" in url
        assert "category_id=1270772586445798" in url
        assert "exact=false" in url


def test_todos_los_listados_piden_radio():
    for url in fb.build_search_urls(incremental=False) + fb.build_search_urls(incremental=True):
        assert "radius=20" in url


def test_radio_configurable(monkeypatch):
    monkeypatch.setattr(fb, "SEARCH_RADIUS", "5")
    assert all("radius=5" in url for url in fb.build_search_urls(incremental=True))

    monkeypatch.setattr(fb, "SEARCH_RADIUS", "")
    assert all("radius=" not in url for url in fb.build_search_urls(incremental=True))


def test_primera_corrida_pide_solo_los_ultimos_30_dias():
    # Traer todo el historico de golpe es lo que restringia la cuenta.
    completo = fb.build_search_urls(incremental=False)

    assert completo
    assert all("daysSinceListed=30" in url for url in completo)


def test_corridas_siguientes_piden_solo_los_ultimos_7_dias():
    incremental = fb.build_search_urls(incremental=True)

    assert incremental
    assert all("daysSinceListed=7" in url for url in incremental)


def test_date_listed_days_pisa_la_ventana_de_los_dos_modos(monkeypatch):
    monkeypatch.setattr(fb, "DATE_LISTED_DAYS", "1")

    for url in fb.build_search_urls(incremental=False) + fb.build_search_urls(incremental=True):
        assert "daysSinceListed=1" in url


def test_date_listed_days_en_cero_recolecta_sin_filtro_de_fecha(monkeypatch):
    monkeypatch.setattr(fb, "DATE_LISTED_DAYS", "0")

    for url in fb.build_search_urls(incremental=False) + fb.build_search_urls(incremental=True):
        assert "daysSinceListed" not in url


def test_ventana_invalida_cae_al_valor_por_defecto():
    assert fb.parse_date_listed_days("no-es-numero", 30, "X") == 30
    assert fb.parse_date_listed_days("", 7, "X") == 7
    assert fb.parse_date_listed_days(None, 7, "X") == 7
    # Marketplace ignora valores fuera de 1/7/30, pero se respeta lo pedido.
    assert fb.parse_date_listed_days("14", 30, "X") == 14


class FakeCursor:
    def __init__(self, resultado):
        self._resultado = resultado
        self.consultas = []

    def execute(self, sql, params=None):
        self.consultas.append((sql, params))

    def fetchone(self):
        return self._resultado

    def close(self):
        pass


class FakeConnection:
    def __init__(self, resultado):
        self._resultado = resultado
        self.cursores = []

    def cursor(self):
        cursor = FakeCursor(self._resultado)
        self.cursores.append(cursor)
        return cursor


def test_hay_publicaciones_previas_detecta_fuente_vacia():
    assert fb.hay_publicaciones_previas(FakeConnection(None), 7) is False


def test_hay_publicaciones_previas_detecta_fuente_con_datos():
    assert fb.hay_publicaciones_previas(FakeConnection((1,)), 7) is True


def test_ya_esta_en_bd_usa_el_codigo_externo_con_prefijo_fb():
    connection = FakeConnection((42,))
    link = "https://www.facebook.com/marketplace/item/123456/"

    assert fb.ya_esta_en_bd(connection, link, fuente_id=7) is True

    _, params = connection.cursores[0].consultas[0]
    assert "FB 123456" in params


def test_ya_esta_en_bd_trata_el_link_como_nuevo_si_falla_la_consulta():
    class ConnectionRota:
        def cursor(self):
            raise RuntimeError("MySQL caido")

    link = "https://www.facebook.com/marketplace/item/123456/"

    # Un fallo puntual de BD no debe cortar la recoleccion.
    assert fb.ya_esta_en_bd(ConnectionRota(), link, fuente_id=7) is False
