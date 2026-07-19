-- Catalogos de barrios y tipos de inmueble para el formulario manual.
-- publicaciones.barrio / publicaciones.tipo_inmueble siguen siendo VARCHAR:
-- estos catalogos solo validan/normalizan, no se agregan FKs.

CREATE TABLE IF NOT EXISTS barrios (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    nombre_normalizado VARCHAR(150) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_barrios_normalizado (nombre_normalizado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tipos_inmueble (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    nombre_normalizado VARCHAR(80) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_tipos_inmueble_normalizado (nombre_normalizado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
