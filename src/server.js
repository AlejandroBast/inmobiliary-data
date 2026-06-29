import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config } from './config.js';
import { getPool, closePool, markInterruptedScans } from './db.js';
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

    const limit = Math.min(Number.parseInt(req.query.limit || '100', 10), 500);
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
        `SELECT p.*, i.*, f.nombre AS fuente_origen, pp.precio_normalizado, pp.valor_m2_calculado,
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
