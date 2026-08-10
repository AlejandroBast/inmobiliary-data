-- Guarda cuando se guardo la nota interna de cada publicacion.
--
-- publicaciones.notas no tenia forma de saber si una observacion es de ayer o
-- de hace seis meses. Nullable y sin DEFAULT CURRENT_TIMESTAMP a proposito:
-- solo debe tener fecha si hay una nota guardada, no todas las filas
-- existentes (que nunca tuvieron nota) deberian aparecer con "fecha de nota"
-- igual a su fecha de captura.

ALTER TABLE publicaciones
    ADD COLUMN fecha_nota TIMESTAMP NULL DEFAULT NULL AFTER notas;
