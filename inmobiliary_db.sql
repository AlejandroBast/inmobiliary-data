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

    fuente_id BIGINT NOT NULL,

    codigo_externo VARCHAR(100),
    link_origen TEXT NOT NULL,
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

    precio DECIMAL(15,0) NOT NULL,

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

    CONSTRAINT chk_precio CHECK (precio > 0),
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
