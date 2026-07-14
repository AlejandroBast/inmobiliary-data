-- SHA-256 del archivo original para confirmar igualdad byte por byte.
ALTER TABLE imagenes_hashes
    ADD COLUMN hash_contenido CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL;
