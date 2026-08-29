-- Revierte 010_precio_historial.sql.
--
-- Se pierde el historial de cambios de precio. publicaciones.precio no se
-- toca: sigue con el valor mas reciente que alcanzo a escribir
-- refresh_publicaciones.py.

DROP TABLE IF EXISTS publicacion_precio_historial;
