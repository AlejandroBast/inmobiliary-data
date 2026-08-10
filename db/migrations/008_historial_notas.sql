-- Historial de notas por publicacion.
--
-- Antes publicaciones.notas guardaba una sola nota: cada click en "Guardar
-- nota" la pisaba, perdiendo lo que hubiera antes. Esta tabla guarda cada
-- nota como su propia fila con fecha, asi el front puede mostrar el
-- historial completo (una tarjeta por nota) en vez de un unico campo.
--
-- publicaciones.notas / fecha_nota (migracion 007) se mantienen como cache
-- liviano de la nota mas reciente -- los sigue usando la columna "Nota" del
-- listado para no tener que resolver una subconsulta por fila ahi. La fuente
-- de verdad del historial completo es esta tabla.

CREATE TABLE IF NOT EXISTS publicacion_notas (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    publicacion_id BIGINT NOT NULL,
    contenido TEXT NOT NULL,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_publicacion_notas_publicacion
        FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    INDEX idx_publicacion_notas_publicacion (publicacion_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Migra la nota unica que ya hubiera en publicaciones.notas como la primera
-- tarjeta del historial, para no perder lo que el cliente ya habia escrito.
INSERT INTO publicacion_notas (publicacion_id, contenido, fecha_creacion)
SELECT id, notas, COALESCE(fecha_nota, fecha_captura)
FROM publicaciones
WHERE notas IS NOT NULL AND TRIM(notas) <> '';
