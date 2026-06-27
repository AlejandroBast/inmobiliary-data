DROP TABLE IF EXISTS publicaciones_inmobiliarias;

CREATE TABLE publicaciones_inmobiliarias (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    localizacion_coordenadas TEXT,

    fecha TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    precio NUMERIC(15,0) NOT NULL CHECK (precio > 0),

    concepto VARCHAR(120),

    barrio_o_ph VARCHAR(150),

    ph_o_especificacion TEXT,

    metros_cuadrados NUMERIC(10,2),

    metros_cuadrados_construidos NUMERIC(10,2),

    valor_m2 NUMERIC(15,0),

    pisos INTEGER CHECK (pisos >= 0),

    habitaciones INTEGER CHECK (habitaciones >= 0),

    banos INTEGER CHECK (banos >= 0),

    parqueadero BOOLEAN,

    antiguedad VARCHAR(100),

    descripcion TEXT,

    observacion TEXT,

    valor_administracion NUMERIC(15,0) CHECK (valor_administracion >= 0),

    link_1 TEXT NOT NULL UNIQUE,

    link_2 TEXT,

    link_3 TEXT,

    imagenes TEXT[],

    perfil_vendedor TEXT
);

CREATE INDEX idx_publicaciones_fecha
ON publicaciones_inmobiliarias (fecha);

CREATE INDEX idx_publicaciones_precio
ON publicaciones_inmobiliarias (precio);

CREATE INDEX idx_publicaciones_barrio_o_ph
ON publicaciones_inmobiliarias (barrio_o_ph);

CREATE INDEX idx_publicaciones_concepto
ON publicaciones_inmobiliarias (concepto);
