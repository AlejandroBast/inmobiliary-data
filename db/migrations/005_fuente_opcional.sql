-- La fuente deja de ser obligatoria en la carga manual.
--
-- El cliente anota inmuebles que vio en cualquier lado y muchas veces no hay un
-- portal detras. Antes fuente_id era NOT NULL con clave foranea: si el
-- formulario no mandaba una fuente, el valor viajaba como 0, la FK lo rechazaba
-- y el front mostraba "La fuente seleccionada no es válida" aunque el usuario no
-- hubiera hecho nada mal.
--
-- La clave foranea se conserva: si SE indica una fuente tiene que existir de
-- verdad. Lo que se permite ahora es no indicar ninguna.

ALTER TABLE publicaciones
    MODIFY COLUMN fuente_id BIGINT NULL;
