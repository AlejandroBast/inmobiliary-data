import inmobiliary.scrapers.facebook as fb


def test_incremental_usa_un_solo_listado_ordenado_por_mas_reciente():
    completo = fb.build_search_urls(incremental=False)
    incremental = fb.build_search_urls(incremental=True)

    assert len(incremental) < len(completo)
    # El corte por links ya guardados solo es correcto si el listado viene
    # ordenado del mas nuevo al mas viejo.
    assert all("creation_time_descend" in url for url in incremental)
    assert not any("minPrice" in url or "maxPrice" in url for url in incremental)


def test_barrido_completo_conserva_los_buckets_de_precio():
    completo = fb.build_search_urls(incremental=False)

    assert len(completo) == len(fb.DEFAULT_PRICE_BUCKETS) + 1
    assert any("minPrice" in url for url in completo)


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
