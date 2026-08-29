-- Historial de precio por publicacion.
--
-- Hasta ahora un cambio de precio en el portal de origen no se reflejaba
-- nunca: los scrapers solo hacen INSERT (ver publicacion_ya_existe en
-- common.py), asi que una publicacion ya guardada quedaba congelada con el
-- precio del dia que se capturo, aunque el vendedor lo bajara o subiera
-- despues. scripts/refresh_publicaciones.py (que agrega esta migracion)
-- vuelve a visitar cada publicacion y, si el precio cambio, actualiza
-- publicaciones.precio -- pero pisar ese campo sin dejar rastro perderia la
-- historia de cuanto costaba antes y cuando cambio, que es justo el dato que
-- el cliente quiere ver ("bajo de $X a $Y el <fecha>").
--
-- Mismo patron que 008_historial_notas.sql: una fila por cada cambio, no un
-- solo campo que se sobreescribe.

CREATE TABLE IF NOT EXISTS publicacion_precio_historial (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    publicacion_id BIGINT NOT NULL,
    precio_anterior DECIMAL(15,0) NULL,
    precio_nuevo DECIMAL(15,0) NOT NULL,
    detectado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_publicacion_precio_historial_publicacion
        FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,

    INDEX idx_publicacion_precio_historial_publicacion (publicacion_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
