use db_inmobiliary_data;

SELECT 
    p.*,
    f.nombre AS fuente_nombre,
    f.url_base AS fuente_url_base,
    f.tipo_fuente AS fuente_tipo,
    f.activa AS fuente_activa,
    f.descripcion AS fuente_descripcion
FROM publicaciones p
INNER JOIN fuentes_inmobiliarias f
    ON p.fuente_id = f.id
ORDER BY p.id ASC;