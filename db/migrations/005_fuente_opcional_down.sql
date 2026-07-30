-- Vuelve a exigir fuente en toda publicacion.
--
-- Falla a proposito si quedan filas con fuente_id en NULL: asignarles una fuente
-- automaticamente seria inventar de donde salio el dato. Resolvelas antes.
--
--   SELECT id, direccion, barrio, descripcion FROM publicaciones
--    WHERE fuente_id IS NULL;
--
-- Para mandarlas todas a la fuente de carga manual:
--   UPDATE publicaciones SET fuente_id = (SELECT id FROM fuentes_inmobiliarias WHERE nombre = 'Cliente')
--    WHERE fuente_id IS NULL;

ALTER TABLE publicaciones
    MODIFY COLUMN fuente_id BIGINT NOT NULL;
