import pytest

from net_retry import with_retry


def test_devuelve_al_primer_intento_sin_esperar():
    llamadas = []

    def operacion():
        llamadas.append(1)
        return "ok"

    assert with_retry(operacion, "prueba", base_delay=0) == "ok"
    assert len(llamadas) == 1


def test_reintenta_y_recupera_tras_un_fallo():
    llamadas = []

    def operacion():
        llamadas.append(1)
        if len(llamadas) < 2:
            raise TimeoutError("timeout puntual")
        return "ok"

    assert with_retry(operacion, "prueba", base_delay=0) == "ok"
    assert len(llamadas) == 2


def test_relanza_la_excepcion_al_agotar_intentos():
    llamadas = []

    def operacion():
        llamadas.append(1)
        raise TimeoutError("siempre falla")

    with pytest.raises(TimeoutError):
        with_retry(operacion, "prueba", attempts=3, base_delay=0)

    assert len(llamadas) == 3


def test_backoff_es_exponencial(monkeypatch):
    esperas = []
    monkeypatch.setattr("net_retry.time.sleep", esperas.append)

    def operacion():
        raise TimeoutError("siempre falla")

    with pytest.raises(TimeoutError):
        with_retry(operacion, "prueba", attempts=4, base_delay=2)

    # Espera entre intentos, no despues del ultimo.
    assert esperas == [2, 4, 8]
