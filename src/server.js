import express from 'express';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { config } from './config.js';
import { getPool, closePool, markInterruptedScans, withTransaction } from './db.js';
import { scanSources } from './services/scanner.js';
import { scannerDaemon } from './services/daemon.js';
import { logger } from './logger.js';

const app = express();
const publicDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'public');

app.use(express.json({ limit: '1mb' }));
app.use(express.static(publicDir));
app.use('/storage', express.static(config.bot.storageDir));

app.get('/api/health', async (_req, res) => {
  try {
    await getPool().query('SELECT 1');
    res.json({ ok: true });
  } catch (error) {
    res.status(500).json({ ok: false, error: formatDbError(error) });
  }
});

app.get('/api/publicaciones', async (req, res) => {
  try {
    const filters = [];
    const params = [];

    if (req.query.fuente) {
      filters.push('f.nombre = ?');
      params.push(req.query.fuente);
    }
    if (req.query.barrio) {
      filters.push('(b.nombre LIKE ? OR i.barrio_texto LIKE ?)');
      params.push(`%${req.query.barrio}%`, `%${req.query.barrio}%`);
    }
    if (req.query.q) {
      filters.push('(p.titulo LIKE ? OR p.descripcion_original LIKE ? OR i.concepto LIKE ?)');
      params.push(`%${req.query.q}%`, `%${req.query.q}%`, `%${req.query.q}%`);
    }
    addNumberFilter(filters, params, 'p.id_publicacion', req.query.id);
    addLikeFilter(filters, params, "DATE_FORMAT(p.fecha_captura, '%Y-%m-%d %H:%i')", req.query.fecha);
    addLikeFilter(filters, params, 'f.nombre', req.query.fuente_col);
    addNumberFilter(filters, params, 'pp.precio_normalizado', req.query.precio);
    addRangeFilter(filters, params, 'pp.precio_normalizado', req.query.precio_min, req.query.precio_max);
    addLikeFilter(filters, params, 'COALESCE(ph.nombre, b.nombre, i.barrio_texto)', req.query.barrio_col);
    addLikeFilter(filters, params, 'i.tipo_inmueble', req.query.tipo);
    addNumberFilter(filters, params, 'c.m2', req.query.m2);
    addNumberFilter(filters, params, 'pp.valor_m2_calculado', req.query.valor_m2);
    addNumberFilter(filters, params, 'c.habitaciones', req.query.habitaciones);
    addNullableNumberFilter(filters, params, 'c.banos', req.query.banos);
    addNumberFilter(filters, params, 'COALESCE(img.total_imagenes, 0)', req.query.imagenes);
    addNotesFilter(filters, params, 'COALESCE(notes.total_anotaciones, 0)', req.query.notas);
    addLikeFilter(filters, params, 'p.enlace_publicacion', req.query.link);

    const limit = Math.min(Number.parseInt(req.query.limit || '500', 10), 500);
    const where = filters.length ? `WHERE ${filters.join(' AND ')}` : '';
    const [rows] = await getPool().execute(
      `SELECT
          p.id_publicacion AS id,
          DATE_FORMAT(p.fecha_captura, '%Y-%m-%d %H:%i') AS fecha,
          f.nombre AS fuente_origen,
          p.enlace_publicacion AS link_1,
          p.enlace_perfil_vendedor AS perfil_vendedor,
          p.estado_publicacion,
          i.estado_registro,
          i.calificacion_confiabilidad,
          i.tipo_inmueble,
          i.concepto,
          COALESCE(ph.nombre, b.nombre, i.barrio_texto) AS barrio_o_ph,
          COALESCE(ph.nombre, i.ph_o_especifico_texto) AS ph_o_especifico,
          CONCAT_WS(', ', i.latitud, i.longitud) AS localizacion_coordenadas,
          pp.precio_normalizado AS precio,
          pp.valor_m2_calculado AS valor_m2,
          c.m2 AS metros_cuadrados,
          c.m2_construidos AS metros_cuadrados_construidos,
          COALESCE(c.piso_apartamento, c.pisos_casa) AS pisos,
          c.habitaciones,
          c.banos,
          CASE
            WHEN c.parqueadero = TRUE THEN COALESCE(c.parqueadero_detalle, 'Si')
            WHEN c.parqueadero = FALSE THEN 'No'
            ELSE NULL
          END AS parqueadero,
          c.antiguedad_inmueble AS antiguedad,
          c.valor_administracion,
          COALESCE(c.descripcion_general, p.descripcion_original) AS descripcion,
          c.observacion,
          COALESCE(img.total_imagenes, 0) AS total_imagenes,
          COALESCE(notes.total_anotaciones, 0) AS total_anotaciones
       FROM publicaciones p
       INNER JOIN inmuebles i ON i.id_inmueble = p.id_inmueble
       INNER JOIN fuentes f ON f.id_fuente = p.id_fuente
       LEFT JOIN barrios b ON b.id_barrio = i.id_barrio
       LEFT JOIN propiedades_horizontales ph ON ph.id_ph = i.id_ph
       LEFT JOIN caracteristicas_inmueble c ON c.id_inmueble = i.id_inmueble
       LEFT JOIN precios_publicacion pp ON pp.id_publicacion = p.id_publicacion AND pp.vigente = TRUE
       LEFT JOIN (
         SELECT id_publicacion, COUNT(*) AS total_imagenes
         FROM imagenes
         GROUP BY id_publicacion
       ) img ON img.id_publicacion = p.id_publicacion
       LEFT JOIN (
         SELECT id_publicacion, COUNT(*) AS total_anotaciones
         FROM anotaciones
         GROUP BY id_publicacion
       ) notes ON notes.id_publicacion = p.id_publicacion
       ${where}
       ORDER BY p.fecha_captura DESC
       LIMIT ${limit}`,
      params
    );
    res.json(rows);
  } catch (error) {
    res.status(500).json({ error: formatDbError(error) });
  }
});

app.get('/api/publicaciones/:id', async (req, res) => {
  try {
    const id = Number.parseInt(req.params.id, 10);
    const [[publicationRows], [imageRows], [noteRows], [evidenceRows]] = await Promise.all([
      getPool().execute(
        `SELECT p.*, p.id_fuente AS publicacion_id_fuente, i.*, f.nombre AS fuente_origen, pp.precio_normalizado, pp.valor_m2_calculado,
                c.m2, c.m2_construidos, c.habitaciones, c.banos, c.parqueadero, c.parqueadero_detalle,
                c.valor_administracion, c.descripcion_general
         FROM publicaciones p
         INNER JOIN inmuebles i ON i.id_inmueble = p.id_inmueble
         INNER JOIN fuentes f ON f.id_fuente = p.id_fuente
         LEFT JOIN precios_publicacion pp ON pp.id_publicacion = p.id_publicacion AND pp.vigente = TRUE
         LEFT JOIN caracteristicas_inmueble c ON c.id_inmueble = i.id_inmueble
         WHERE p.id_publicacion = ?
         LIMIT 1`,
        [id]
      ),
      getPool().execute('SELECT * FROM imagenes WHERE id_publicacion = ? ORDER BY orden', [id]),
      getPool().execute('SELECT * FROM anotaciones WHERE id_publicacion = ? ORDER BY fecha_creacion DESC', [id]),
      getPool().execute('SELECT * FROM evidencias_publicacion WHERE id_publicacion = ? ORDER BY fecha_creacion DESC', [id])
    ]);
    if (!publicationRows.length) return res.status(404).json({ error: 'Publicacion no encontrada' });
    res.json({
      publicacion: publicationRows[0],
      imagenes: imageRows,
      anotaciones: noteRows,
      evidencias: evidenceRows
    });
  } catch (error) {
    res.status(500).json({ error: formatDbError(error) });
  }
});

app.post('/api/publicaciones', async (req, res) => {
  try {
    const payload = normalizePublicationPayload(req.body);
    const id = await withTransaction(async (connection) => createPublication(connection, payload));
    res.status(201).json({ ok: true, id_publicacion: id });
  } catch (error) {
    res.status(500).json({ ok: false, error: formatDbError(error) });
  }
});

app.put('/api/publicaciones/:id', async (req, res) => {
  try {
    const id = Number.parseInt(req.params.id, 10);
    if (!Number.isFinite(id)) return res.status(400).json({ error: 'ID invalido.' });
    const payload = normalizePublicationPayload(req.body);
    await withTransaction(async (connection) => updatePublication(connection, id, payload));
    res.json({ ok: true, id_publicacion: id });
  } catch (error) {
    res.status(500).json({ ok: false, error: formatDbError(error) });
  }
});

app.delete('/api/publicaciones/:id', async (req, res) => {
  try {
    const id = Number.parseInt(req.params.id, 10);
    if (!Number.isFinite(id)) return res.status(400).json({ error: 'ID invalido.' });
    await withTransaction(async (connection) => deletePublication(connection, id));
    res.json({ ok: true });
  } catch (error) {
    res.status(500).json({ ok: false, error: formatDbError(error) });
  }
});

app.post('/api/publicaciones/:id/anotaciones', async (req, res) => {
  try {
    const id = Number.parseInt(req.params.id, 10);
    const texto = String(req.body.texto || '').trim();
    if (!texto) return res.status(400).json({ error: 'La anotacion no puede estar vacia.' });
    const [result] = await getPool().execute(
      'INSERT INTO anotaciones (id_publicacion, texto) VALUES (?, ?)',
      [id, texto]
    );
    res.status(201).json({ id_anotacion: result.insertId });
  } catch (error) {
    res.status(500).json({ error: formatDbError(error) });
  }
});

app.get('/api/fuentes', async (_req, res) => {
  try {
    const [rows] = await getPool().execute('SELECT id_fuente, nombre, estado FROM fuentes ORDER BY nombre');
    res.json(rows);
  } catch (error) {
    res.status(500).json({ error: formatDbError(error) });
  }
});

app.get('/api/escaneos', async (_req, res) => {
  try {
    const [rows] = await getPool().execute(
      `SELECT e.*, f.nombre AS fuente
       FROM escaneos e
       INNER JOIN fuentes f ON f.id_fuente = e.id_fuente
       ORDER BY e.iniciado_en DESC
       LIMIT 50`
    );
    res.json(rows);
  } catch (error) {
    res.status(500).json({ error: formatDbError(error) });
  }
});

app.get('/api/bot/status', (_req, res) => {
  res.json(scannerDaemon.getStatus());
});

app.post('/api/bot/start', (_req, res) => {
  res.json(scannerDaemon.start({ runImmediately: true }));
});

app.post('/api/bot/stop', (_req, res) => {
  res.json(scannerDaemon.stop());
});

app.post('/api/bot/run-now', async (_req, res) => {
  try {
    const result = scannerDaemon.triggerRunNow({ reason: 'frontend' });
    res.json(result);
  } catch (error) {
    res.status(500).json({ ok: false, error: formatDbError(error) });
  }
});

app.post('/api/scan', async (req, res) => {
  try {
    const source = req.body.source || null;
    const summaries = await scanSources({
      all: !source || source === 'all',
      sourceKeys: source && source !== 'all' ? [source] : [],
      maxPages: req.body.maxPages ? Number.parseInt(req.body.maxPages, 10) : undefined,
      maxListingsPerSource: req.body.maxListings ? Number.parseInt(req.body.maxListings, 10) : undefined
    });
    res.json({ ok: true, summaries });
  } catch (error) {
    logger.error(error);
    res.status(500).json({ ok: false, error: formatDbError(error) });
  }
});

const server = app.listen(config.web.port, config.web.host, () => {
  logger.info(`Frontend basico disponible en http://${config.web.host}:${config.web.port}`);
  if (config.bot.autoScan) {
    markInterruptedScans()
      .catch((error) => logger.warn({ error: error.message }, 'No se pudieron marcar escaneos interrumpidos'))
      .finally(() => scannerDaemon.start({ runImmediately: config.bot.scanOnStart }));
  }
});

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

async function shutdown() {
  scannerDaemon.stop();
  server.close();
  await closePool();
  process.exit(0);
}

function normalizePublicationPayload(body = {}) {
  const payload = {
    idFuente: numberOrNull(body.id_fuente),
    titulo: cleanString(body.titulo, 350),
    url: cleanString(body.enlace_publicacion, 1200),
    codigo: cleanString(body.codigo_publicacion_fuente, 180),
    estado: cleanEnum(body.estado_publicacion, ['activa', 'inactiva', 'pausada', 'vendida', 'descartada', 'error', 'desconocida'], 'activa'),
    tipo: cleanEnum(body.tipo_inmueble, ['apartamento', 'casa', 'lote', 'local', 'oficina', 'bodega', 'finca', 'otro'], 'otro'),
    barrio: cleanString(body.barrio_texto, 180),
    descripcion: cleanString(body.descripcion, 6000),
    precio: numberOrNull(body.precio_normalizado),
    m2: numberOrNull(body.m2),
    habitaciones: intOrNull(body.habitaciones),
    banos: intOrNull(body.banos),
    administracion: numberOrNull(body.valor_administracion)
  };

  if (!payload.idFuente) throw new Error('Selecciona una fuente.');
  if (!payload.url) throw new Error('El link de la publicacion es obligatorio.');
  payload.codigo = payload.codigo || extractCodeFromUrl(payload.url) || `manual-${Date.now()}`;
  payload.titulo = payload.titulo || 'Publicacion manual';
  payload.descripcion = payload.descripcion || payload.titulo;
  return payload;
}

async function createPublication(connection, payload) {
  await assertSourceExists(connection, payload.idFuente);
  const barrioId = payload.barrio ? await upsertBarrio(connection, payload.barrio) : null;
  const [inmuebleResult] = await connection.execute(
    `INSERT INTO inmuebles
      (tipo_inmueble, tipo_oferta, concepto, ciudad, departamento, id_barrio,
       barrio_texto, localizacion_texto, calificacion_confiabilidad, estado_registro, activo)
     VALUES (?, 'venta', ?, 'Pasto', 'Narino', ?, ?, ?, 85, 'validado', TRUE)`,
    [
      payload.tipo,
      payload.titulo,
      barrioId,
      payload.barrio,
      payload.barrio ? `${payload.barrio}, Pasto, Narino` : 'Pasto, Narino'
    ]
  );
  const inmuebleId = inmuebleResult.insertId;
  await upsertCaracteristicas(connection, inmuebleId, payload);

  const [publicationResult] = await connection.execute(
    `INSERT INTO publicaciones
      (id_inmueble, id_fuente, codigo_publicacion_fuente, titulo, enlace_publicacion,
       fecha_captura, fecha_ultima_revision, descripcion_original, estado_publicacion, datos_crudos, hash_contenido)
     VALUES (?, ?, ?, ?, ?, NOW(), NOW(), ?, ?, ?, ?)`,
    [
      inmuebleId,
      payload.idFuente,
      payload.codigo,
      payload.titulo,
      payload.url,
      payload.descripcion,
      payload.estado,
      JSON.stringify({ origen: 'crud_manual' }),
      hashPublication(payload.idFuente, payload.codigo, payload.url)
    ]
  );
  await replaceCurrentPrice(connection, publicationResult.insertId, payload);
  return publicationResult.insertId;
}

async function updatePublication(connection, publicationId, payload) {
  await assertSourceExists(connection, payload.idFuente);
  const [rows] = await connection.execute(
    'SELECT id_inmueble FROM publicaciones WHERE id_publicacion = ? LIMIT 1',
    [publicationId]
  );
  if (!rows.length) throw new Error('Publicacion no encontrada.');

  const inmuebleId = rows[0].id_inmueble;
  const barrioId = payload.barrio ? await upsertBarrio(connection, payload.barrio) : null;
  await connection.execute(
    `UPDATE inmuebles
     SET tipo_inmueble = ?, concepto = ?, id_barrio = ?, barrio_texto = ?,
         localizacion_texto = ?, estado_registro = 'validado', activo = TRUE
     WHERE id_inmueble = ?`,
    [
      payload.tipo,
      payload.titulo,
      barrioId,
      payload.barrio,
      payload.barrio ? `${payload.barrio}, Pasto, Narino` : 'Pasto, Narino',
      inmuebleId
    ]
  );
  await upsertCaracteristicas(connection, inmuebleId, payload);
  await connection.execute(
    `UPDATE publicaciones
     SET id_fuente = ?, codigo_publicacion_fuente = ?, titulo = ?, enlace_publicacion = ?,
         fecha_ultima_revision = NOW(), descripcion_original = ?, estado_publicacion = ?,
         hash_contenido = ?
     WHERE id_publicacion = ?`,
    [
      payload.idFuente,
      payload.codigo,
      payload.titulo,
      payload.url,
      payload.descripcion,
      payload.estado,
      hashPublication(payload.idFuente, payload.codigo, payload.url),
      publicationId
    ]
  );
  await replaceCurrentPrice(connection, publicationId, payload);
}

async function deletePublication(connection, publicationId) {
  const [rows] = await connection.execute(
    'SELECT id_inmueble FROM publicaciones WHERE id_publicacion = ? LIMIT 1',
    [publicationId]
  );
  if (!rows.length) throw new Error('Publicacion no encontrada.');
  const inmuebleId = rows[0].id_inmueble;
  await connection.execute('DELETE FROM publicaciones WHERE id_publicacion = ?', [publicationId]);
  const [[countRow]] = await connection.execute(
    'SELECT COUNT(*) AS total FROM publicaciones WHERE id_inmueble = ?',
    [inmuebleId]
  );
  if (Number(countRow.total) === 0) {
    await connection.execute('DELETE FROM inmuebles WHERE id_inmueble = ?', [inmuebleId]);
  }
}

async function assertSourceExists(connection, sourceId) {
  const [rows] = await connection.execute('SELECT id_fuente FROM fuentes WHERE id_fuente = ? LIMIT 1', [sourceId]);
  if (!rows.length) throw new Error('La fuente seleccionada no existe.');
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

async function upsertCaracteristicas(connection, inmuebleId, payload) {
  await connection.execute(
    `INSERT INTO caracteristicas_inmueble
      (id_inmueble, m2, habitaciones, banos, valor_administracion, descripcion_general)
     VALUES (?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
       m2 = VALUES(m2),
       habitaciones = VALUES(habitaciones),
       banos = VALUES(banos),
       valor_administracion = VALUES(valor_administracion),
       descripcion_general = VALUES(descripcion_general)`,
    [inmuebleId, payload.m2, payload.habitaciones, payload.banos, payload.administracion, payload.descripcion]
  );
}

async function replaceCurrentPrice(connection, publicationId, payload) {
  await connection.execute('UPDATE precios_publicacion SET vigente = FALSE WHERE id_publicacion = ?', [publicationId]);
  if (payload.precio === null) return;
  await connection.execute(
    `INSERT INTO precios_publicacion
      (id_publicacion, precio_original, precio_normalizado, moneda, m2_usado_calculo, confianza_precio, vigente, fecha_captura)
     VALUES (?, ?, ?, 'COP', ?, 100, TRUE, NOW())`,
    [publicationId, String(payload.precio), payload.precio, payload.m2]
  );
}

function cleanString(value, maxLength) {
  const text = String(value || '').trim();
  return text ? text.slice(0, maxLength) : null;
}

function addLikeFilter(filters, params, expression, value) {
  const text = String(value || '').trim();
  if (!text) return;
  filters.push(`${expression} LIKE ?`);
  params.push(`%${text}%`);
}

function addNumberFilter(filters, params, expression, value) {
  const text = normalizeNumberInput(value);
  if (text === '') return;
  const number = Number(text);
  if (!Number.isFinite(number)) return addLikeFilter(filters, params, `CAST(${expression} AS CHAR)`, value);
  filters.push(`${expression} = ?`);
  params.push(number);
}

function addNullableNumberFilter(filters, params, expression, value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return;
  if (['sin_info', 'sin-informacion', 'sin informacion', 'sin', 'null', 'vacio'].includes(text)) {
    filters.push(`${expression} IS NULL`);
    return;
  }
  if (['con_info', 'con-informacion', 'con informacion', 'con'].includes(text)) {
    filters.push(`${expression} IS NOT NULL`);
    return;
  }
  addNumberFilter(filters, params, expression, value);
}

function addNotesFilter(filters, params, expression, value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return;
  if (['con', 'si', 'sí', 'has', 'true', '1', 'con_notas'].includes(text)) {
    filters.push(`${expression} > 0`);
    return;
  }
  if (['sin', 'no', 'none', 'false', '0', 'sin_notas'].includes(text)) {
    filters.push(`${expression} = 0`);
    return;
  }
  addNumberFilter(filters, params, expression, value);
}

function addRangeFilter(filters, params, expression, minValue, maxValue) {
  const minText = normalizePriceInput(minValue);
  const maxText = normalizePriceInput(maxValue);
  const min = minText === '' ? null : Number(minText);
  const max = maxText === '' ? null : Number(maxText);

  if (Number.isFinite(min)) {
    filters.push(`${expression} >= ?`);
    params.push(min);
  }
  if (Number.isFinite(max)) {
    filters.push(`${expression} <= ?`);
    params.push(max);
  }
}

function normalizePriceInput(value) {
  const raw = String(value || '').toLowerCase();
  const usesMillionSuffix = /(^|[\d\s.,])(m|mm|millon|millones)\b/.test(raw);
  const text = normalizeNumberInput(raw.replace(/(m|mm|millon|millones)\b/g, ''));
  if (text === '') return '';
  const number = Number(text);
  if (!Number.isFinite(number)) return text;
  return String((usesMillionSuffix || (number > 0 && number < 1000)) ? number * 1_000_000 : number);
}

function normalizeNumberInput(value) {
  let text = String(value || '').replace(/[$\s]/g, '').trim();
  if (!text) return '';
  if (text.includes(',') && text.includes('.')) {
    return text.replace(/\./g, '').replace(',', '.');
  }
  if (text.includes(',')) {
    return /^\d+,\d{1,2}$/.test(text) ? text.replace(',', '.') : text.replace(/,/g, '');
  }
  if ((text.match(/\./g) || []).length > 1) {
    return text.replace(/\./g, '');
  }
  if (/^\d+\.\d{3}$/.test(text)) {
    return text.replace('.', '');
  }
  return text;
}

function cleanEnum(value, allowed, fallback) {
  return allowed.includes(value) ? value : fallback;
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return null;
  return number;
}

function intOrNull(value) {
  const number = numberOrNull(value);
  return number === null ? null : Math.trunc(number);
}

function extractCodeFromUrl(url) {
  const match = String(url).match(/(?:-|\/)([0-9]{5,})(?:[/?#]|$)/);
  return match?.[1] || null;
}

function hashPublication(sourceId, code, url) {
  return crypto.createHash('sha256').update(`${sourceId}|${code}|${url}`).digest('hex');
}

function formatDbError(error) {
  const message = String(error?.message || error);
  if (message.includes('ECONNREFUSED') && message.includes('3306')) {
    return 'No se pudo conectar a MySQL en 127.0.0.1:3306. Inicia MySQL o ajusta DB_HOST, DB_PORT, DB_USER y DB_PASSWORD en outputs/inmobiliary_bot/.env.';
  }
  if (message.includes('ER_BAD_DB_ERROR')) {
    return 'La base de datos inmobiliary_data no existe. Importa outputs/inmobiliary_db.sql o ejecuta pnpm run db:init.';
  }
  if (message.includes('ER_ACCESS_DENIED_ERROR')) {
    return 'MySQL rechazo el usuario o la contrasena. Revisa DB_USER y DB_PASSWORD en outputs/inmobiliary_bot/.env.';
  }
  return message;
}
