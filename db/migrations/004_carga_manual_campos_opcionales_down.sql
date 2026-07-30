-- Revierte la carga manual libre: link_origen y precio vuelven a ser obligatorios.
--
-- Falla a proposito si quedan filas con link_origen o precio en NULL. Revertir
-- con datos incompletos obligaria a inventar un link o un precio, y eso es peor
-- que fallar: resolve o borra esas filas antes de correr esta reversa.
--
--   SELECT id, direccion, barrio FROM publicaciones
--    WHERE link_origen IS NULL OR precio IS NULL;

ALTER TABLE publicaciones DROP CHECK chk_precio;
ALTER TABLE publicaciones
    ADD CONSTRAINT chk_precio CHECK (precio > 0);

ALTER TABLE publicaciones
    MODIFY COLUMN link_origen TEXT NOT NULL,
    MODIFY COLUMN precio DECIMAL(15,0) NOT NULL;
