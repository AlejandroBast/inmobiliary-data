-- Revierte 009_comentarios_comparacion.sql.
--
-- Se pierde toda la bitacora: los comentarios escritos al comparar y, sobre
-- todo, los motivos de eliminacion de inmuebles que ya no existen en
-- publicaciones. Eso no se puede reconstruir desde ninguna otra tabla, asi que
-- conviene exportar comentarios_comparacion antes de correr esto.

DROP TABLE IF EXISTS comentarios_comparacion;
