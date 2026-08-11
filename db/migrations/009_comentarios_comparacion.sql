-- Comentarios de la comparacion de duplicados, con el motivo de cada borrado.
--
-- Pedido del cliente: al comparar inmuebles repetidos tiene que poder dejar
-- escrito por que se elimina uno.
--
-- Esa justificacion no puede vivir en publicacion_notas (migracion 008): esa
-- tabla cuelga de publicaciones con ON DELETE CASCADE, asi que el motivo del
-- borrado se borraria en el mismo momento en que pasa a importar. Por eso aca
-- publicacion_id es un BIGINT suelto, SIN clave foranea, y cada fila guarda
-- ademas una copia de los datos que identifican al inmueble: cuando la
-- publicacion ya no existe, la bitacora se sigue leyendo sola.

CREATE TABLE IF NOT EXISTS comentarios_comparacion (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Inmueble comentado. Sin FK a proposito (ver arriba).
    publicacion_id BIGINT NOT NULL,

    -- Publicacion desde la que se abrio la comparacion, para saber contra que
    -- grupo se estaba decidiendo. Tambien sin FK: la raiz tambien se puede
    -- eliminar despues.
    publicacion_raiz_id BIGINT NULL,

    -- 'comentario': observacion suelta escrita mientras se comparaba.
    -- 'eliminacion': motivo con el que se elimino el inmueble.
    tipo ENUM('comentario', 'eliminacion') NOT NULL DEFAULT 'comentario',
    contenido TEXT NOT NULL,

    -- Copia de los campos con los que se reconoce el inmueble en la tarjeta de
    -- comparacion. Redundante mientras la publicacion existe; es lo unico que
    -- queda una vez eliminada.
    snapshot_tipo_inmueble VARCHAR(80) NULL,
    snapshot_barrio VARCHAR(150) NULL,
    snapshot_fuente VARCHAR(100) NULL,
    snapshot_precio DECIMAL(15,0) NULL,
    snapshot_link TEXT NULL,

    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_comentarios_comparacion_publicacion (publicacion_id),
    INDEX idx_comentarios_comparacion_raiz (publicacion_raiz_id),
    INDEX idx_comentarios_comparacion_tipo (tipo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
