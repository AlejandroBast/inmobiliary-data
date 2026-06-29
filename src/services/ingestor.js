import { findSourceByName, getPool, withTransaction } from '../db.js';
import { sha256, normalizeText } from './parser.js';

export async function ingestListing(listing) {
  if (listing.discardReason) {
    return {
      status: 'descartado',
      reason: listing.discardReason,
      publicationId: null,
      inmuebleId: null
    };
  }

  return withTransaction(async (connection) => {
    const source = await findSourceByName(listing.sourceName, connection);
    if (!source) throw new Error(`La fuente "${listing.sourceName}" no existe en la tabla fuentes.`);

    const barrioId = listing.barrio ? await upsertBarrio(connection, listing.barrio) : null;
    const sellerId = await upsertSeller(connection, source.id_fuente, listing);
    const existingPublication = await findExistingPublication(connection, source.id_fuente, listing);
    const duplicate = existingPublication ? null : await findSimilarInmueble(connection, listing, barrioId);
    const inmuebleId = existingPublication?.id_inmueble
      || duplicate?.id_inmueble
      || await insertInmueble(connection, listing, barrioId);

    await upsertCaracteristicas(connection, inmuebleId, listing);
    const publication = await upsertPublicacion(connection, inmuebleId, source.id_fuente, sellerId, listing);
    await upsertPrecio(connection, publication.id_publicacion, listing);
    await upsertEnlace(connection, inmuebleId, publication.id_publicacion, source.id_fuente, listing.url);

    if (duplicate && duplicate.score >= 70 && duplicate.id_inmueble !== inmuebleId) {
      await insertDuplicateSuggestion(connection, duplicate.id_inmueble, inmuebleId, duplicate.score, duplicate.criteria);
    }

    return {
      status: publication.created ? 'nuevo' : 'actualizado',
      reason: null,
      publicationId: publication.id_publicacion,
      inmuebleId,
      sourceId: source.id_fuente
    };
  });
}

export async function saveListingAssets({ publicationId, inmuebleId, evidences, images }) {
  if (!publicationId) return;
  await withTransaction(async (connection) => {
    for (const evidence of evidences || []) {
      await connection.execute(
        `INSERT INTO evidencias_publicacion
          (id_publicacion, tipo_evidencia, ruta_archivo, descripcion, hash_archivo)
         VALUES (?, ?, ?, ?, ?)`,
        [publicationId, evidence.type, evidence.path, evidence.description || null, evidence.hash || null]
      );
    }

    for (const image of images || []) {
      const [existing] = await connection.execute(
        'SELECT id_imagen FROM imagenes WHERE id_publicacion = ? AND hash_imagen = ? LIMIT 1',
        [publicationId, image.hash]
      );
      if (existing.length) continue;
      await connection.execute(
        `INSERT INTO imagenes
          (id_publicacion, id_inmueble, ruta_archivo, url_original, nombre_archivo, orden,
           hash_imagen, formato, peso_kb, ancho_px, alto_px, es_portada, fecha_descarga)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())`,
        [
          publicationId,
          inmuebleId,
          image.path,
          image.urlOriginal,
          image.fileName,
          image.order,
          image.hash,
          image.format,
          image.weightKb,
          image.width,
          image.height,
          image.isCover
        ]
      );
    }
  });
}

async function upsertBarrio(connection, name) {
  await connection.execute(
    `INSERT INTO barrios (nombre, ciudad, departamento, activo)
     VALUES (?, 'Pasto', 'Narino', TRUE)
     ON DUPLICATE KEY UPDATE activo = TRUE`,
    [name]
  );
  const [rows] = await connection.execute(
    `SELECT id_barrio FROM barrios
     WHERE nombre = ? AND ciudad = 'Pasto' AND departamento = 'Narino'
     LIMIT 1`,
    [name]
  );
  return rows[0]?.id_barrio || null;
}

async function upsertSeller(connection, sourceId, listing) {
  if (!listing.sellerProfileUrl) return null;
  const [rows] = await connection.execute(
    'SELECT id_vendedor FROM vendedores_publicadores WHERE id_fuente = ? AND url_perfil = ? LIMIT 1',
    [sourceId, listing.sellerProfileUrl]
  );
  if (rows.length) return rows[0].id_vendedor;
  const [result] = await connection.execute(
    `INSERT INTO vendedores_publicadores
      (id_fuente, nombre_visible, tipo_vendedor, url_perfil, observacion)
     VALUES (?, ?, 'desconocido', ?, ?)`,
    [sourceId, null, listing.sellerProfileUrl, 'Perfil visible capturado desde la publicacion']
  );
  return result.insertId;
}

async function findExistingPublication(connection, sourceId, listing) {
  const [rows] = await connection.execute(
    `SELECT id_publicacion, id_inmueble
     FROM publicaciones
     WHERE id_fuente = ?
       AND (
         codigo_publicacion_fuente = ?
         OR enlace_publicacion = ?
         OR hash_contenido = ?
       )
     LIMIT 1`,
    [sourceId, listing.externalCode, listing.url, listing.contentHash]
  );
  return rows[0] || null;
}

async function findSimilarInmueble(connection, listing, barrioId) {
  const [rows] = await connection.execute(
    `SELECT
        i.id_inmueble,
        i.tipo_inmueble,
        COALESCE(i.barrio_texto, b.nombre) AS barrio,
        c.m2,
        c.habitaciones,
        c.banos,
        pp.precio_normalizado,
        p.descripcion_original
     FROM inmuebles i
     LEFT JOIN barrios b ON b.id_barrio = i.id_barrio
     LEFT JOIN caracteristicas_inmueble c ON c.id_inmueble = i.id_inmueble
     LEFT JOIN publicaciones p ON p.id_inmueble = i.id_inmueble
     LEFT JOIN precios_publicacion pp ON pp.id_publicacion = p.id_publicacion AND pp.vigente = TRUE
     WHERE i.ciudad = 'Pasto'
       AND i.tipo_inmueble = ?
       AND (? IS NULL OR i.id_barrio = ? OR i.barrio_texto = ?)
     ORDER BY i.fecha_actualizacion DESC
     LIMIT 25`,
    [listing.propertyType, barrioId, barrioId, listing.barrio]
  );

  let best = null;
  for (const row of rows) {
    const score = scoreDuplicate(row, listing);
    if (!best || score.score > best.score) best = { ...row, ...score };
  }
  return best && best.score >= 78 ? best : null;
}

function scoreDuplicate(row, listing) {
  let score = 0;
  const criteria = {};
  if (row.tipo_inmueble === listing.propertyType) {
    score += 20;
    criteria.tipo = true;
  }
  if (normalizeText(row.barrio || '') === normalizeText(listing.barrio || '')) {
    score += 20;
    criteria.barrio = true;
  }
  if (row.precio_normalizado && listing.priceNormalized) {
    const diff = Math.abs(Number(row.precio_normalizado) - listing.priceNormalized) / listing.priceNormalized;
    if (diff <= 0.05) {
      score += 20;
      criteria.precio = true;
    }
  }
  if (row.m2 && listing.area) {
    const diff = Math.abs(Number(row.m2) - listing.area) / listing.area;
    if (diff <= 0.10) {
      score += 15;
      criteria.area = true;
    }
  }
  if (row.habitaciones && listing.rooms && Number(row.habitaciones) === Number(listing.rooms)) {
    score += 10;
    criteria.habitaciones = true;
  }
  if (row.banos && listing.baths && Number(row.banos) === Number(listing.baths)) {
    score += 10;
    criteria.banos = true;
  }
  if (row.descripcion_original && listing.description) {
    const a = new Set(normalizeText(row.descripcion_original).split(' ').filter((w) => w.length > 4));
    const b = normalizeText(listing.description).split(' ').filter((w) => a.has(w)).length;
    if (b >= 8) {
      score += 15;
      criteria.descripcion = true;
    }
  }
  return { score: Math.min(score, 100), criteria };
}

async function insertInmueble(connection, listing, barrioId) {
  const [result] = await connection.execute(
    `INSERT INTO inmuebles
      (tipo_inmueble, tipo_oferta, concepto, ciudad, departamento, id_barrio,
       barrio_texto, localizacion_texto, calificacion_confiabilidad, estado_registro, activo)
     VALUES (?, 'venta', ?, 'Pasto', 'Narino', ?, ?, ?, ?, ?, TRUE)`,
    [
      listing.propertyType,
      listing.concept,
      barrioId,
      listing.barrio,
      listing.locationText,
      listing.confidence,
      listing.confidence >= 70 && !listing.validationWarnings?.length ? 'validado' : 'pendiente_revision'
    ]
  );
  return result.insertId;
}

async function upsertCaracteristicas(connection, inmuebleId, listing) {
  await connection.execute(
    `INSERT INTO caracteristicas_inmueble
      (id_inmueble, m2, m2_construidos, piso_apartamento, pisos_casa, habitaciones,
       banos, parqueadero, parqueadero_detalle, valor_administracion, descripcion_general)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
       m2 = COALESCE(VALUES(m2), m2),
       m2_construidos = COALESCE(VALUES(m2_construidos), m2_construidos),
       piso_apartamento = COALESCE(VALUES(piso_apartamento), piso_apartamento),
       pisos_casa = COALESCE(VALUES(pisos_casa), pisos_casa),
       habitaciones = COALESCE(VALUES(habitaciones), habitaciones),
       banos = COALESCE(VALUES(banos), banos),
       parqueadero = COALESCE(VALUES(parqueadero), parqueadero),
       parqueadero_detalle = COALESCE(VALUES(parqueadero_detalle), parqueadero_detalle),
       valor_administracion = COALESCE(VALUES(valor_administracion), valor_administracion),
       descripcion_general = COALESCE(VALUES(descripcion_general), descripcion_general)`,
    [
      inmuebleId,
      listing.area,
      listing.builtArea,
      listing.floorApartment,
      listing.houseFloors,
      listing.rooms,
      listing.baths,
      listing.parking,
      listing.parkingDetail,
      listing.adminFee,
      listing.description
    ]
  );
}

async function upsertPublicacion(connection, inmuebleId, sourceId, sellerId, listing) {
  const [before] = await connection.execute(
    'SELECT id_publicacion FROM publicaciones WHERE id_fuente = ? AND codigo_publicacion_fuente = ? LIMIT 1',
    [sourceId, listing.externalCode]
  );
  await connection.execute(
    `INSERT INTO publicaciones
      (id_inmueble, id_fuente, id_vendedor, codigo_publicacion_fuente, titulo,
       enlace_publicacion, enlace_perfil_vendedor, fecha_captura, fecha_ultima_revision,
       descripcion_original, estado_publicacion, datos_crudos, hash_contenido)
     VALUES (?, ?, ?, ?, ?, ?, ?, NOW(), NOW(), ?, 'activa', ?, ?)
     ON DUPLICATE KEY UPDATE
       id_inmueble = VALUES(id_inmueble),
       id_vendedor = COALESCE(VALUES(id_vendedor), id_vendedor),
       titulo = VALUES(titulo),
       enlace_publicacion = VALUES(enlace_publicacion),
       enlace_perfil_vendedor = COALESCE(VALUES(enlace_perfil_vendedor), enlace_perfil_vendedor),
       fecha_ultima_revision = NOW(),
       descripcion_original = VALUES(descripcion_original),
       estado_publicacion = 'activa',
       datos_crudos = VALUES(datos_crudos)`,
    [
      inmuebleId,
      sourceId,
      sellerId,
      listing.externalCode,
      listing.title,
      listing.url,
      listing.sellerProfileUrl,
      listing.description,
      JSON.stringify({ text: listing.rawText?.slice(0, 20000), images: listing.images, warnings: listing.validationWarnings || [] }),
      listing.contentHash || sha256(`${sourceId}|${listing.externalCode}`)
    ]
  );
  const [rows] = await connection.execute(
    'SELECT id_publicacion FROM publicaciones WHERE id_fuente = ? AND codigo_publicacion_fuente = ? LIMIT 1',
    [sourceId, listing.externalCode]
  );
  return { id_publicacion: rows[0].id_publicacion, created: before.length === 0 };
}

async function upsertPrecio(connection, publicationId, listing) {
  if (!listing.priceNormalized) return;
  const [rows] = await connection.execute(
    `SELECT id_precio, precio_normalizado
     FROM precios_publicacion
     WHERE id_publicacion = ? AND vigente = TRUE
     LIMIT 1`,
    [publicationId]
  );
  const current = rows[0];
  if (current && Number(current.precio_normalizado) === Number(listing.priceNormalized)) return;
  if (current) {
    await connection.execute('UPDATE precios_publicacion SET vigente = FALSE WHERE id_precio = ?', [current.id_precio]);
  }
  await connection.execute(
    `INSERT INTO precios_publicacion
      (id_publicacion, precio_original, precio_normalizado, moneda, m2_usado_calculo,
       confianza_precio, vigente, fecha_captura)
     VALUES (?, ?, ?, 'COP', ?, ?, TRUE, NOW())`,
    [
      publicationId,
      listing.priceOriginal,
      listing.priceNormalized,
      listing.area || listing.builtArea,
      listing.priceConfidence
    ]
  );
}

async function upsertEnlace(connection, inmuebleId, publicationId, sourceId, url) {
  const [rows] = await connection.execute(
    'SELECT id_enlace FROM enlaces_relacionados WHERE url = ? LIMIT 1',
    [url]
  );
  if (rows.length) return;
  await connection.execute(
    `INSERT INTO enlaces_relacionados
      (id_inmueble, id_publicacion, id_fuente, url, estado, fecha_detectado)
     VALUES (?, ?, ?, ?, 'activo', NOW())`,
    [inmuebleId, publicationId, sourceId, url]
  );
}

async function insertDuplicateSuggestion(connection, principalId, duplicateId, score, criteria) {
  await connection.execute(
    `INSERT IGNORE INTO duplicados_sugeridos
      (id_inmueble_principal, id_inmueble_posible_duplicado, puntaje_similitud, criterios, estado_revision)
     VALUES (?, ?, ?, ?, 'pendiente')`,
    [principalId, duplicateId, score, JSON.stringify(criteria)]
  );
}
