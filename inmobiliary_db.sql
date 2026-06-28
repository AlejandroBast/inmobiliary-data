-- ============================================================
-- Inmobiliary-Data
-- Script de base de datos para MySQL 8.0 o superior
-- Version segura para produccion: no elimina tablas ni datos existentes.
-- Solo base de datos: no usuarios, no roles, no login.
-- ============================================================

CREATE DATABASE IF NOT EXISTS inmobiliary_data
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE inmobiliary_data;

-- ============================================================
-- Catalogos y ubicaciones
-- ============================================================

CREATE TABLE IF NOT EXISTS fuentes (
  id_fuente BIGINT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  url_base VARCHAR(500) NOT NULL,
  estado ENUM('activa', 'inactiva', 'pausada') NOT NULL DEFAULT 'activa',
  frecuencia_minutos INT NOT NULL DEFAULT 1440,
  observacion VARCHAR(500) NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT uk_fuentes_nombre UNIQUE (nombre),
  CONSTRAINT chk_fuentes_frecuencia CHECK (frecuencia_minutos > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS barrios (
  id_barrio BIGINT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(160) NOT NULL,
  ciudad VARCHAR(120) NOT NULL DEFAULT 'Pasto',
  departamento VARCHAR(120) NOT NULL DEFAULT 'Narino',
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT uk_barrios_nombre_ciudad_departamento UNIQUE (nombre, ciudad, departamento),
  INDEX idx_barrios_nombre (nombre),
  INDEX idx_barrios_ciudad_departamento (ciudad, departamento),
  INDEX idx_barrios_activo (activo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS propiedades_horizontales (
  id_ph BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_barrio BIGINT NULL,
  nombre VARCHAR(180) NOT NULL,
  tipo ENUM('edificio', 'conjunto', 'condominio', 'urbanizacion', 'unidad_residencial', 'otro') NOT NULL DEFAULT 'otro',
  localizacion_texto VARCHAR(500) NULL,
  latitud DECIMAL(10,8) NULL,
  longitud DECIMAL(11,8) NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_ph_barrio
    FOREIGN KEY (id_barrio) REFERENCES barrios (id_barrio)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT uk_ph_nombre_barrio UNIQUE (nombre, id_barrio),
  CONSTRAINT chk_ph_latitud CHECK (latitud IS NULL OR latitud BETWEEN -90 AND 90),
  CONSTRAINT chk_ph_longitud CHECK (longitud IS NULL OR longitud BETWEEN -180 AND 180),
  INDEX idx_ph_barrio (id_barrio),
  INDEX idx_ph_nombre (nombre),
  INDEX idx_ph_tipo (tipo),
  INDEX idx_ph_coordenadas (latitud, longitud),
  INDEX idx_ph_activo (activo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vendedores_publicadores (
  id_vendedor BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_fuente BIGINT NOT NULL,
  nombre_visible VARCHAR(180) NULL,
  tipo_vendedor ENUM('persona', 'inmobiliaria', 'constructor', 'agente', 'desconocido') NOT NULL DEFAULT 'desconocido',
  url_perfil VARCHAR(1000) NULL,
  contacto_visible VARCHAR(250) NULL,
  observacion VARCHAR(500) NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_vendedores_fuente
    FOREIGN KEY (id_fuente) REFERENCES fuentes (id_fuente)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  INDEX idx_vendedores_fuente (id_fuente),
  INDEX idx_vendedores_nombre (nombre_visible),
  INDEX idx_vendedores_tipo (tipo_vendedor),
  INDEX idx_vendedores_url_perfil (url_perfil(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Inmuebles reales y caracteristicas
-- ============================================================

CREATE TABLE IF NOT EXISTS inmuebles (
  id_inmueble BIGINT AUTO_INCREMENT PRIMARY KEY,
  tipo_inmueble ENUM('apartamento', 'casa', 'lote', 'local', 'oficina', 'bodega', 'finca', 'otro') NOT NULL DEFAULT 'otro',
  tipo_oferta ENUM('venta') NOT NULL DEFAULT 'venta',
  concepto VARCHAR(250) NULL,
  ciudad VARCHAR(120) NOT NULL DEFAULT 'Pasto',
  departamento VARCHAR(120) NOT NULL DEFAULT 'Narino',
  id_barrio BIGINT NULL,
  id_ph BIGINT NULL,
  barrio_texto VARCHAR(180) NULL,
  ph_o_especifico_texto VARCHAR(180) NULL,
  localizacion_texto VARCHAR(500) NULL,
  direccion_referencia VARCHAR(500) NULL,
  latitud DECIMAL(10,8) NULL,
  longitud DECIMAL(11,8) NULL,
  calificacion_confiabilidad DECIMAL(5,2) NOT NULL DEFAULT 0.00,
  estado_registro ENUM('nuevo', 'pendiente_revision', 'validado', 'descartado', 'duplicado', 'inactivo') NOT NULL DEFAULT 'nuevo',
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_inmuebles_barrio
    FOREIGN KEY (id_barrio) REFERENCES barrios (id_barrio)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_inmuebles_ph
    FOREIGN KEY (id_ph) REFERENCES propiedades_horizontales (id_ph)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT chk_inmuebles_latitud CHECK (latitud IS NULL OR latitud BETWEEN -90 AND 90),
  CONSTRAINT chk_inmuebles_longitud CHECK (longitud IS NULL OR longitud BETWEEN -180 AND 180),
  CONSTRAINT chk_inmuebles_confiabilidad CHECK (calificacion_confiabilidad BETWEEN 0 AND 100),
  INDEX idx_inmuebles_tipo (tipo_inmueble),
  INDEX idx_inmuebles_oferta (tipo_oferta),
  INDEX idx_inmuebles_estado (estado_registro),
  INDEX idx_inmuebles_barrio (id_barrio),
  INDEX idx_inmuebles_ph (id_ph),
  INDEX idx_inmuebles_ciudad_departamento (ciudad, departamento),
  INDEX idx_inmuebles_coordenadas (latitud, longitud),
  INDEX idx_inmuebles_activo (activo),
  FULLTEXT INDEX ftx_inmuebles_ubicacion (concepto, barrio_texto, ph_o_especifico_texto, localizacion_texto, direccion_referencia)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS caracteristicas_inmueble (
  id_caracteristica BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_inmueble BIGINT NOT NULL,
  m2 DECIMAL(12,2) NULL,
  m2_construidos DECIMAL(12,2) NULL,
  piso_apartamento INT NULL,
  pisos_casa INT NULL,
  habitaciones INT NULL,
  banos INT NULL,
  parqueadero BOOLEAN NULL,
  parqueadero_detalle VARCHAR(250) NULL,
  antiguedad_inmueble VARCHAR(120) NULL,
  valor_administracion DECIMAL(15,2) NULL,
  descripcion_general TEXT NULL,
  observacion TEXT NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_caracteristicas_inmueble
    FOREIGN KEY (id_inmueble) REFERENCES inmuebles (id_inmueble)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT uk_caracteristicas_inmueble UNIQUE (id_inmueble),
  CONSTRAINT chk_caracteristicas_m2 CHECK (m2 IS NULL OR m2 >= 0),
  CONSTRAINT chk_caracteristicas_m2_construidos CHECK (m2_construidos IS NULL OR m2_construidos >= 0),
  CONSTRAINT chk_caracteristicas_habitaciones CHECK (habitaciones IS NULL OR habitaciones >= 0),
  CONSTRAINT chk_caracteristicas_banos CHECK (banos IS NULL OR banos >= 0),
  CONSTRAINT chk_caracteristicas_administracion CHECK (valor_administracion IS NULL OR valor_administracion >= 0),
  INDEX idx_caracteristicas_m2 (m2),
  INDEX idx_caracteristicas_m2_construidos (m2_construidos),
  INDEX idx_caracteristicas_habitaciones (habitaciones),
  INDEX idx_caracteristicas_banos (banos),
  INDEX idx_caracteristicas_parqueadero (parqueadero),
  INDEX idx_caracteristicas_administracion (valor_administracion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Publicaciones, precios, imagenes y evidencias
-- ============================================================

CREATE TABLE IF NOT EXISTS publicaciones (
  id_publicacion BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_inmueble BIGINT NOT NULL,
  id_fuente BIGINT NOT NULL,
  id_vendedor BIGINT NULL,
  codigo_publicacion_fuente VARCHAR(180) NULL,
  titulo VARCHAR(350) NULL,
  enlace_publicacion VARCHAR(1200) NOT NULL,
  enlace_perfil_vendedor VARCHAR(1000) NULL,
  fecha_publicacion DATETIME NULL,
  fecha_captura DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_ultima_revision DATETIME NULL,
  descripcion_original TEXT NULL,
  estado_publicacion ENUM('activa', 'inactiva', 'pausada', 'vendida', 'descartada', 'error', 'desconocida') NOT NULL DEFAULT 'activa',
  motivo_descarte VARCHAR(500) NULL,
  datos_crudos JSON NULL,
  hash_contenido CHAR(64) NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_publicaciones_inmueble
    FOREIGN KEY (id_inmueble) REFERENCES inmuebles (id_inmueble)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_publicaciones_fuente
    FOREIGN KEY (id_fuente) REFERENCES fuentes (id_fuente)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_publicaciones_vendedor
    FOREIGN KEY (id_vendedor) REFERENCES vendedores_publicadores (id_vendedor)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT uk_publicaciones_fuente_codigo UNIQUE (id_fuente, codigo_publicacion_fuente),
  CONSTRAINT uk_publicaciones_hash UNIQUE (hash_contenido),
  INDEX idx_publicaciones_inmueble (id_inmueble),
  INDEX idx_publicaciones_fuente (id_fuente),
  INDEX idx_publicaciones_vendedor (id_vendedor),
  INDEX idx_publicaciones_estado (estado_publicacion),
  INDEX idx_publicaciones_fecha_captura (fecha_captura),
  INDEX idx_publicaciones_fecha_publicacion (fecha_publicacion),
  INDEX idx_publicaciones_enlace (enlace_publicacion(255)),
  FULLTEXT INDEX ftx_publicaciones_texto (titulo, descripcion_original)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS precios_publicacion (
  id_precio BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_publicacion BIGINT NOT NULL,
  precio_original VARCHAR(120) NULL,
  precio_normalizado DECIMAL(18,2) NULL,
  moneda CHAR(3) NOT NULL DEFAULT 'COP',
  m2_usado_calculo DECIMAL(12,2) NULL,
  valor_m2_calculado DECIMAL(18,2)
    GENERATED ALWAYS AS (
      CASE
        WHEN precio_normalizado IS NOT NULL
          AND m2_usado_calculo IS NOT NULL
          AND m2_usado_calculo > 0
        THEN ROUND(precio_normalizado / m2_usado_calculo, 2)
        ELSE NULL
      END
    ) STORED,
  confianza_precio DECIMAL(5,2) NOT NULL DEFAULT 0.00,
  vigente BOOLEAN NOT NULL DEFAULT TRUE,
  id_publicacion_vigente BIGINT
    GENERATED ALWAYS AS (CASE WHEN vigente = TRUE THEN id_publicacion ELSE NULL END) STORED,
  observacion VARCHAR(500) NULL,
  fecha_captura DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_precios_publicacion
    FOREIGN KEY (id_publicacion) REFERENCES publicaciones (id_publicacion)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT uk_precio_vigente_por_publicacion UNIQUE (id_publicacion_vigente),
  CONSTRAINT chk_precios_precio CHECK (precio_normalizado IS NULL OR precio_normalizado >= 0),
  CONSTRAINT chk_precios_m2 CHECK (m2_usado_calculo IS NULL OR m2_usado_calculo >= 0),
  CONSTRAINT chk_precios_confianza CHECK (confianza_precio BETWEEN 0 AND 100),
  INDEX idx_precios_publicacion (id_publicacion),
  INDEX idx_precios_precio (precio_normalizado),
  INDEX idx_precios_valor_m2 (valor_m2_calculado),
  INDEX idx_precios_moneda (moneda),
  INDEX idx_precios_vigente (vigente),
  INDEX idx_precios_fecha (fecha_captura)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS imagenes (
  id_imagen BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_publicacion BIGINT NOT NULL,
  id_inmueble BIGINT NOT NULL,
  ruta_archivo VARCHAR(1000) NULL,
  url_original VARCHAR(1200) NULL,
  nombre_archivo VARCHAR(255) NULL,
  orden INT NOT NULL DEFAULT 1,
  hash_imagen CHAR(64) NULL,
  formato VARCHAR(20) NULL,
  peso_kb DECIMAL(12,2) NULL,
  ancho_px INT NULL,
  alto_px INT NULL,
  es_portada BOOLEAN NOT NULL DEFAULT FALSE,
  fecha_descarga DATETIME NULL,

  CONSTRAINT fk_imagenes_publicacion
    FOREIGN KEY (id_publicacion) REFERENCES publicaciones (id_publicacion)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_imagenes_inmueble
    FOREIGN KEY (id_inmueble) REFERENCES inmuebles (id_inmueble)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT chk_imagenes_referencia CHECK (ruta_archivo IS NOT NULL OR url_original IS NOT NULL),
  CONSTRAINT chk_imagenes_orden CHECK (orden > 0),
  CONSTRAINT chk_imagenes_peso CHECK (peso_kb IS NULL OR peso_kb >= 0),
  CONSTRAINT chk_imagenes_ancho CHECK (ancho_px IS NULL OR ancho_px >= 0),
  CONSTRAINT chk_imagenes_alto CHECK (alto_px IS NULL OR alto_px >= 0),
  INDEX idx_imagenes_publicacion (id_publicacion),
  INDEX idx_imagenes_inmueble (id_inmueble),
  INDEX idx_imagenes_portada (es_portada),
  INDEX idx_imagenes_hash (hash_imagen),
  INDEX idx_imagenes_orden (id_publicacion, orden),
  INDEX idx_imagenes_url (url_original(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS enlaces_relacionados (
  id_enlace BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_inmueble BIGINT NOT NULL,
  id_publicacion BIGINT NULL,
  id_fuente BIGINT NOT NULL,
  url VARCHAR(1200) NOT NULL,
  estado ENUM('activo', 'inactivo', 'roto', 'duplicado', 'pendiente_revision') NOT NULL DEFAULT 'activo',
  observacion VARCHAR(500) NULL,
  fecha_detectado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_enlaces_inmueble
    FOREIGN KEY (id_inmueble) REFERENCES inmuebles (id_inmueble)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_enlaces_publicacion
    FOREIGN KEY (id_publicacion) REFERENCES publicaciones (id_publicacion)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_enlaces_fuente
    FOREIGN KEY (id_fuente) REFERENCES fuentes (id_fuente)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  INDEX idx_enlaces_inmueble (id_inmueble),
  INDEX idx_enlaces_publicacion (id_publicacion),
  INDEX idx_enlaces_fuente (id_fuente),
  INDEX idx_enlaces_estado (estado),
  INDEX idx_enlaces_url (url(255)),
  INDEX idx_enlaces_fecha (fecha_detectado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evidencias_publicacion (
  id_evidencia BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_publicacion BIGINT NOT NULL,
  tipo_evidencia ENUM('pdf', 'html', 'captura', 'json', 'texto', 'otro') NOT NULL,
  ruta_archivo VARCHAR(1000) NOT NULL,
  descripcion VARCHAR(500) NULL,
  hash_archivo CHAR(64) NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_evidencias_publicacion
    FOREIGN KEY (id_publicacion) REFERENCES publicaciones (id_publicacion)
    ON UPDATE CASCADE ON DELETE CASCADE,
  INDEX idx_evidencias_publicacion (id_publicacion),
  INDEX idx_evidencias_tipo (tipo_evidencia),
  INDEX idx_evidencias_hash (hash_archivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS anotaciones (
  id_anotacion BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_publicacion BIGINT NOT NULL,
  texto TEXT NOT NULL,
  fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  CONSTRAINT fk_anotaciones_publicacion
    FOREIGN KEY (id_publicacion) REFERENCES publicaciones (id_publicacion)
    ON UPDATE CASCADE ON DELETE CASCADE,
  INDEX idx_anotaciones_publicacion (id_publicacion),
  INDEX idx_anotaciones_fecha (fecha_creacion),
  FULLTEXT INDEX ftx_anotaciones_texto (texto)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Duplicados sugeridos y procesos del bot
-- ============================================================

CREATE TABLE IF NOT EXISTS duplicados_sugeridos (
  id_duplicado BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_inmueble_principal BIGINT NOT NULL,
  id_inmueble_posible_duplicado BIGINT NOT NULL,
  puntaje_similitud DECIMAL(5,2) NOT NULL DEFAULT 0.00,
  criterios JSON NULL,
  estado_revision ENUM('pendiente', 'confirmado', 'rechazado', 'fusionado') NOT NULL DEFAULT 'pendiente',
  fecha_deteccion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_revision DATETIME NULL,
  observacion VARCHAR(700) NULL,

  CONSTRAINT fk_duplicados_principal
    FOREIGN KEY (id_inmueble_principal) REFERENCES inmuebles (id_inmueble)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_duplicados_posible
    FOREIGN KEY (id_inmueble_posible_duplicado) REFERENCES inmuebles (id_inmueble)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT uk_duplicados_par UNIQUE (id_inmueble_principal, id_inmueble_posible_duplicado),
  CONSTRAINT chk_duplicados_no_mismo CHECK (id_inmueble_principal <> id_inmueble_posible_duplicado),
  CONSTRAINT chk_duplicados_puntaje CHECK (puntaje_similitud BETWEEN 0 AND 100),
  INDEX idx_duplicados_principal (id_inmueble_principal),
  INDEX idx_duplicados_posible (id_inmueble_posible_duplicado),
  INDEX idx_duplicados_estado (estado_revision),
  INDEX idx_duplicados_puntaje (puntaje_similitud),
  INDEX idx_duplicados_fecha (fecha_deteccion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS escaneos (
  id_escaneo BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_fuente BIGINT NOT NULL,
  estado ENUM('iniciado', 'en_proceso', 'finalizado', 'finalizado_con_errores', 'fallido', 'cancelado') NOT NULL DEFAULT 'iniciado',
  parametros JSON NULL,
  total_encontradas INT NOT NULL DEFAULT 0,
  total_guardadas INT NOT NULL DEFAULT 0,
  total_descartadas INT NOT NULL DEFAULT 0,
  total_errores INT NOT NULL DEFAULT 0,
  mensaje_error TEXT NULL,
  iniciado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finalizado_en DATETIME NULL,

  CONSTRAINT fk_escaneos_fuente
    FOREIGN KEY (id_fuente) REFERENCES fuentes (id_fuente)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_escaneos_totales CHECK (
    total_encontradas >= 0
    AND total_guardadas >= 0
    AND total_descartadas >= 0
    AND total_errores >= 0
  ),
  INDEX idx_escaneos_fuente (id_fuente),
  INDEX idx_escaneos_estado (estado),
  INDEX idx_escaneos_inicio (iniciado_en),
  INDEX idx_escaneos_fin (finalizado_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resultados_escaneo (
  id_resultado BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_escaneo BIGINT NOT NULL,
  id_publicacion BIGINT NULL,
  url_detectada VARCHAR(1200) NOT NULL,
  estado ENUM('detectado', 'nuevo', 'actualizado', 'duplicado', 'descartado', 'error') NOT NULL DEFAULT 'detectado',
  motivo VARCHAR(500) NULL,
  datos_extraidos JSON NULL,
  fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT fk_resultados_escaneo
    FOREIGN KEY (id_escaneo) REFERENCES escaneos (id_escaneo)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_resultados_publicacion
    FOREIGN KEY (id_publicacion) REFERENCES publicaciones (id_publicacion)
    ON UPDATE CASCADE ON DELETE SET NULL,
  INDEX idx_resultados_escaneo (id_escaneo),
  INDEX idx_resultados_publicacion (id_publicacion),
  INDEX idx_resultados_estado (estado),
  INDEX idx_resultados_url (url_detectada(255)),
  INDEX idx_resultados_fecha (fecha_registro)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Datos iniciales: fuentes autorizadas
-- ============================================================

INSERT INTO fuentes
  (nombre, url_base, estado, frecuencia_minutos, observacion)
VALUES
  ('Facebook Marketplace', 'https://www.facebook.com/marketplace/', 'activa', 1440, 'Fuente autorizada para publicaciones visibles en Marketplace.'),
  ('Metrocuadrado', 'https://www.metrocuadrado.com/', 'activa', 1440, 'Fuente autorizada de publicaciones inmobiliarias.'),
  ('Ciencuadras', 'https://www.ciencuadras.com/', 'activa', 1440, 'Fuente autorizada de publicaciones inmobiliarias.'),
  ('FincaRaiz', 'https://www.fincaraiz.com.co/', 'activa', 1440, 'Fuente autorizada de publicaciones inmobiliarias.'),
  ('Clasificados Amorel', 'https://clasificadosamorel.com/', 'activa', 1440, 'Fuente autorizada local.')
ON DUPLICATE KEY UPDATE
  url_base = VALUES(url_base),
  estado = VALUES(estado),
  frecuencia_minutos = VALUES(frecuencia_minutos),
  observacion = VALUES(observacion);
