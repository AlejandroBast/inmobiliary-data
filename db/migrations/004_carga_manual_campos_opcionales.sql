-- Carga manual libre: el cliente agrega inmuebles que vio en cualquier lado
-- (un cartel, un conocido, una foto) y muchas veces no hay link publicado ni un
-- precio cerrado. link_origen y precio eran NOT NULL y bloqueaban el alta.
--
-- fuente_id se deja NOT NULL a proposito: es una clave foranea y describe de
-- donde salio el dato. El front deja de exigirla eligiendo "Cliente" por
-- defecto, asi que no le agrega friccion a quien carga.

ALTER TABLE publicaciones
    MODIFY COLUMN link_origen TEXT NULL,
    MODIFY COLUMN precio DECIMAL(15,0) NULL;

-- uq_link_origen sigue vigente: MySQL admite varios NULL en un indice UNIQUE,
-- asi que muchas publicaciones sin link conviven sin chocar entre si.

-- El CHECK original (precio > 0) da UNKNOWN con NULL y por lo tanto ya pasaba,
-- pero se reescribe explicito para que la intencion quede en el esquema.
ALTER TABLE publicaciones DROP CHECK chk_precio;
ALTER TABLE publicaciones
    ADD CONSTRAINT chk_precio CHECK (precio IS NULL OR precio > 0);
