-- Revierte 008_historial_notas.sql.
--
-- Se pierde el historial completo de notas (cualquier tarjeta agregada
-- despues de la primera). publicaciones.notas / fecha_nota no se tocan:
-- siguen con la nota mas reciente que alcanzaron a cachear.

DROP TABLE IF EXISTS publicacion_notas;
