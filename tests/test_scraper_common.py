from pathlib import Path

import scraper_common as common


# ==========================================================
# TEXTO
# ==========================================================

def test_clean_text_normaliza_espacios():
    assert common.clean_text("  Casa   en    venta \n") == "Casa en venta"


def test_clean_text_desescapa_entidades_html():
    # Fincaraiz, Metrocuadrado y Ciencuadras guardaban esto sin desescapar.
    assert common.clean_text("Ni&ntilde;o &amp; Ni&ntilde;a") == "Niño & Niña"
    assert common.clean_text("86 m&sup2;") == "86 m²"


def test_clean_text_devuelve_none_para_vacio():
    assert common.clean_text(None) is None
    assert common.clean_text("   ") is None


def test_only_digits():
    assert common.only_digits("$ 250.000.000") == 250000000
    assert common.only_digits("sin numeros") is None
    assert common.only_digits(None) is None


def test_parse_int_toma_el_primer_numero():
    assert common.parse_int("3 habitaciones") == 3
    assert common.parse_int(None) is None


def test_parse_decimal_acepta_coma_decimal():
    assert common.parse_decimal("118,65 m2") == 118.65
    assert common.parse_decimal("100 m2") == 100.0
    assert common.parse_decimal("sin area") is None
    assert common.parse_decimal(None) is None


def test_parse_decimal_trata_el_punto_como_separador_de_miles():
    # Ciencuadras devolvia 1.104 aca: un lote de 1104 m2 guardado como 1.1 m2.
    assert common.parse_decimal("1.104 m2") == 1104.0
    assert common.parse_decimal("1.234,56") == 1234.56
    # Pero 118.65 sigue siendo decimal, no ciento dieciocho mil.
    assert common.parse_decimal("118.65 m2") == 118.65


def test_get_lines_descarta_vacias():
    assert common.get_lines("uno\n\n  dos  \n") == ["uno", "dos"]
    assert common.get_lines(None) == []


# ==========================================================
# ARCHIVOS
# ==========================================================

def test_sanitize_filename_reemplaza_caracteres_invalidos():
    assert common.sanitize_filename("CASA/123 #4") == "CASA_123__4"


def test_sanitize_filename_usa_respaldo_si_viene_vacio():
    assert common.sanitize_filename(None)
    assert common.sanitize_filename("") != ""


def test_file_hash_devuelve_none_si_no_existe():
    # Fincaraiz y Ciencuadras reventaban con FileNotFoundError.
    assert common.file_hash(None) is None
    assert common.file_hash("no_existe_este_archivo.txt") is None


def test_file_hash_calcula_sha256(tmp_path):
    archivo = tmp_path / "dato.txt"
    archivo.write_bytes(b"hola")

    # sha256("hola")
    assert common.file_hash(archivo) == (
        "b221d9dbb083a7f33428d7c2a3c3198ae925614d70210e28716ccaa7cd4ddb79"
    )


def test_evidence_dirs_crea_las_tres_carpetas(tmp_path):
    html_dir, img_dir, screenshot_dir = common.get_publication_evidence_dirs(7, tmp_path)

    assert html_dir.is_dir() and img_dir.is_dir() and screenshot_dir.is_dir()
    assert html_dir.parent.name == "publicacion_7"


def test_evidence_dirs_omite_screenshots_cuando_no_hacen_falta(tmp_path):
    html_dir, img_dir, screenshot_dir = common.get_publication_evidence_dirs(
        7, tmp_path, con_screenshots=False
    )

    assert html_dir.is_dir() and img_dir.is_dir()
    assert screenshot_dir is None
    assert not (Path(tmp_path) / "publicacion_7" / "screenshots").exists()


# ==========================================================
# BASE DE DATOS
# ==========================================================

class FakeCursor:
    def __init__(self, resultados):
        self._resultados = list(resultados)
        self.consultas = []
        self.lastrowid = 99

    def execute(self, sql, params=None):
        self.consultas.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self._resultados.pop(0) if self._resultados else None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, *resultados):
        self._resultados = resultados
        self.cursores = []
        self.commits = 0

    def cursor(self):
        cursor = FakeCursor(self._resultados)
        self.cursores.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1


def test_publicacion_ya_existe_valida_por_codigo_externo_cuando_hay():
    connection = FakeConnection((5,))

    assert common.publicacion_ya_existe(connection, "http://x", 1, "ABC") == 5

    sql, params = connection.cursores[0].consultas[0]
    assert "fuente_id = %s AND codigo_externo = %s" in sql
    assert params == ("http://x", 1, "ABC")


def test_publicacion_ya_existe_solo_por_link_si_no_hay_codigo():
    connection = FakeConnection(None)

    assert common.publicacion_ya_existe(connection, "http://x") is None

    sql, params = connection.cursores[0].consultas[0]
    assert "codigo_externo" not in sql
    assert params == ("http://x",)


def test_insert_evidencia_guarda_el_hash(tmp_path):
    # Metrocuadrado insertaba sin hash_archivo: el detector de duplicados por
    # imagen nunca tuvo con que comparar sus evidencias.
    archivo = tmp_path / "foto.jpg"
    archivo.write_bytes(b"hola")
    connection = FakeConnection(None)

    common.insert_evidencia(connection, 1, "imagen", archivo, "http://foto")

    sql, params = connection.cursores[0].consultas[1]
    assert "hash_archivo" in sql
    assert params[-1] == common.file_hash(archivo)
    assert connection.commits == 1


def test_insert_evidencia_no_duplica_si_ya_estaba():
    connection = FakeConnection((1,))

    common.insert_evidencia(connection, 1, "html", "ruta.html")

    assert len(connection.cursores[0].consultas) == 1
    assert connection.commits == 0
