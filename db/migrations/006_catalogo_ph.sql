-- Catalogo de PH (conjuntos, edificios, condominios) de Pasto.
--
-- Mismo patron que barrios/tipos_inmueble (migracion 003): publicaciones.ph
-- sigue siendo VARCHAR, este catalogo solo valida/normaliza y alimenta el
-- filtro del front. Se puebla con scripts/seed_catalogos.py --apply a partir
-- de data/pasto_ph.tsv.

CREATE TABLE IF NOT EXISTS ph_conjuntos (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    nombre_normalizado VARCHAR(150) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ph_conjuntos_normalizado (nombre_normalizado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
