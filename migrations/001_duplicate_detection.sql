-- Deteccion reversible de publicaciones que representan el mismo inmueble.
-- Esta migracion no elimina ni combina registros de publicaciones.

CREATE TABLE IF NOT EXISTS inmuebles_detectados (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    estado ENUM('automatico', 'pendiente', 'confirmado') NOT NULL DEFAULT 'pendiente',
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS publicaciones_inmueble (
    inmueble_id BIGINT NOT NULL,
    publicacion_id BIGINT NOT NULL,
    puntaje DECIMAL(5,2),
    razones JSON,
    fecha_asociacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (inmueble_id, publicacion_id),
    UNIQUE KEY uq_publicacion_inmueble (publicacion_id),
    CONSTRAINT fk_pi_inmueble FOREIGN KEY (inmueble_id)
        REFERENCES inmuebles_detectados(id) ON DELETE CASCADE,
    CONSTRAINT fk_pi_publicacion FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS imagenes_hashes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    evidencia_id BIGINT NOT NULL,
    publicacion_id BIGINT NOT NULL,
    algoritmo VARCHAR(20) NOT NULL DEFAULT 'dhash64',
    hash_perceptual CHAR(16) NOT NULL,
    hash_contenido CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    ancho INT,
    alto INT,
    fecha_calculo TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_evidencia_algoritmo (evidencia_id, algoritmo),
    KEY idx_hash_publicacion (publicacion_id),
    CONSTRAINT fk_ih_evidencia FOREIGN KEY (evidencia_id)
        REFERENCES evidencias_publicacion(id) ON DELETE CASCADE,
    CONSTRAINT fk_ih_publicacion FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS coincidencias_publicaciones (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    publicacion_id BIGINT NOT NULL,
    candidata_id BIGINT NOT NULL,
    puntaje DECIMAL(5,2) NOT NULL,
    estado ENUM('pendiente', 'confirmada', 'descartada') NOT NULL DEFAULT 'pendiente',
    distancia_metros DECIMAL(12,2),
    imagenes_coincidentes INT NOT NULL DEFAULT 0,
    distancia_hash_minima INT,
    razones JSON NOT NULL,
    fecha_deteccion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_revision TIMESTAMP NULL,
    -- La aplicacion siempre guarda primero el ID menor para evitar A-B y B-A.
    UNIQUE KEY uq_par_publicaciones (publicacion_id, candidata_id),
    KEY idx_coincidencia_estado (estado, puntaje),
    CONSTRAINT chk_publicaciones_distintas CHECK (publicacion_id <> candidata_id),
    CONSTRAINT fk_cp_publicacion FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id) ON DELETE CASCADE,
    CONSTRAINT fk_cp_candidata FOREIGN KEY (candidata_id)
        REFERENCES publicaciones(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
