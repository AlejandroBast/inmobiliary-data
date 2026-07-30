DROP DATABASE IF EXISTS db_inmobiliary_data;

CREATE DATABASE db_inmobiliary_data
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE db_inmobiliary_data;


CREATE TABLE fuentes_inmobiliarias (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    nombre VARCHAR(100) NOT NULL UNIQUE,
    url_base TEXT,
    tipo_fuente VARCHAR(50), -- portal, marketplace, inmobiliaria, manual
    activa BOOLEAN DEFAULT TRUE,

    descripcion TEXT
) ENGINE=InnoDB 
DEFAULT CHARSET=utf8mb4 
COLLATE=utf8mb4_unicode_ci;


CREATE TABLE publicaciones (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    -- Opcional (antes migracion 005, fusionada aca): en la carga manual no
    -- siempre hay un portal detras. La FK sigue: si se indica, tiene que existir.
    fuente_id BIGINT NULL,

    codigo_externo VARCHAR(100),
    -- Opcional (antes migracion 004, fusionada aca): en la carga manual el
    -- cliente anota inmuebles que vio en cualquier lado y no siempre hay link
    -- publicado. uq_link_origen sigue valiendo porque MySQL admite varios NULL.
    link_origen TEXT NULL,
    links_adicionales JSON,

    fecha_captura TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    coordenadas TEXT,
    latitud DECIMAL(10,7),
    longitud DECIMAL(10,7),

    direccion TEXT,
    ciudad VARCHAR(100) DEFAULT 'Pasto',
    barrio VARCHAR(150),

    tipo_inmueble VARCHAR(80),
    ph TEXT,
    estrato INT,

    descripcion TEXT,

    -- Opcional (antes migracion 004): no siempre hay un precio cerrado.
    precio DECIMAL(15,0) NULL,

    m2 DECIMAL(10,2),

    precio_m2 DECIMAL(15,0) GENERATED ALWAYS AS (
        CASE 
            WHEN m2 IS NOT NULL AND m2 > 0 
            THEN precio / m2 
            ELSE NULL 
        END
    ) STORED,

    m2_construido DECIMAL(10,2),

    precio_m2_construido DECIMAL(15,0) GENERATED ALWAYS AS (
        CASE 
            WHEN m2_construido IS NOT NULL AND m2_construido > 0 
            THEN precio / m2_construido 
            ELSE NULL 
        END
    ) STORED,

    antiguedad VARCHAR(100),
    pisos INT,
    habitaciones INT,
    banios INT,
    parqueadero INT,
    administracion DECIMAL(15,0),

    notas TEXT,

    CONSTRAINT fk_publicaciones_fuente
        FOREIGN KEY (fuente_id)
        REFERENCES fuentes_inmobiliarias(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    UNIQUE KEY uq_link_origen (link_origen(500)),

    CONSTRAINT chk_precio CHECK (precio IS NULL OR precio > 0),
    CONSTRAINT chk_m2 CHECK (m2 IS NULL OR m2 >= 0),
    CONSTRAINT chk_m2_construido CHECK (m2_construido IS NULL OR m2_construido >= 0),
    CONSTRAINT chk_habitaciones CHECK (habitaciones IS NULL OR habitaciones >= 0),
    CONSTRAINT chk_banios CHECK (banios IS NULL OR banios >= 0),
    CONSTRAINT chk_parqueadero CHECK (parqueadero IS NULL OR parqueadero >= 0),
    CONSTRAINT chk_administracion CHECK (administracion IS NULL OR administracion >= 0)
) ENGINE=InnoDB 
DEFAULT CHARSET=utf8mb4 
COLLATE=utf8mb4_unicode_ci;


CREATE TABLE evidencias_publicacion (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    publicacion_id BIGINT NOT NULL,

    tipo VARCHAR(50) NOT NULL, -- html, imagen, screenshot
    ruta_archivo TEXT,
    url_original TEXT,
    hash_archivo VARCHAR(255),

    fecha_guardado TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_evidencias_publicacion
        FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
) ENGINE=InnoDB 
DEFAULT CHARSET=utf8mb4 
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- DETECCION DE PUBLICACIONES DEL MISMO INMUEBLE
-- =========================================================

CREATE TABLE inmuebles_detectados (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    estado ENUM('automatico', 'pendiente', 'confirmado') NOT NULL DEFAULT 'pendiente',
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


CREATE TABLE publicaciones_inmueble (
    inmueble_id BIGINT NOT NULL,
    publicacion_id BIGINT NOT NULL,
    puntaje DECIMAL(5,2),
    razones JSON,
    fecha_asociacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (inmueble_id, publicacion_id),
    UNIQUE KEY uq_publicacion_inmueble (publicacion_id),

    CONSTRAINT fk_pi_inmueble
        FOREIGN KEY (inmueble_id)
        REFERENCES inmuebles_detectados(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_pi_publicacion
        FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


CREATE TABLE imagenes_hashes (
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

    CONSTRAINT fk_ih_evidencia
        FOREIGN KEY (evidencia_id)
        REFERENCES evidencias_publicacion(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_ih_publicacion
        FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


CREATE TABLE coincidencias_publicaciones (
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

    -- La aplicacion guarda primero el ID menor para evitar pares A-B y B-A.
    UNIQUE KEY uq_par_publicaciones (publicacion_id, candidata_id),
    KEY idx_coincidencia_estado (estado, puntaje),

    CONSTRAINT chk_publicaciones_distintas
        CHECK (publicacion_id <> candidata_id),

    CONSTRAINT fk_cp_publicacion
        FOREIGN KEY (publicacion_id)
        REFERENCES publicaciones(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_cp_candidata
        FOREIGN KEY (candidata_id)
        REFERENCES publicaciones(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- =========================================================
-- CATALOGOS DE BARRIOS Y TIPOS DE INMUEBLE
-- =========================================================
-- Fusionado aca desde la migracion 003 (db/migrations/003_catalogos_ubicacion_tipo.sql):
-- recrear la base solo con este archivo dejaba estas dos tablas sin crear,
-- rompiendo el front con "Table 'barrios' doesn't exist" hasta que alguien
-- se acordaba de correr esa migracion aparte. Quedan vacias: para poblarlas
-- corre scripts/seed_catalogos.py --apply despues de crear la base.

CREATE TABLE barrios (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    nombre_normalizado VARCHAR(150) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_barrios_normalizado (nombre_normalizado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE tipos_inmueble (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    nombre_normalizado VARCHAR(80) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_tipos_inmueble_normalizado (nombre_normalizado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
