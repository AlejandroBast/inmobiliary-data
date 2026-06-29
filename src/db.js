import fs from 'node:fs/promises';
import mysql from 'mysql2/promise';
import { config } from './config.js';

let pool;

export function getPool() {
  if (!pool) {
    pool = mysql.createPool(config.db);
  }
  return pool;
}

export async function closePool() {
  if (pool) {
    await pool.end();
    pool = null;
  }
}

export async function initDatabase() {
  const sql = await fs.readFile(config.schemaPath, 'utf8');
  const connection = await mysql.createConnection({
    host: config.db.host,
    port: config.db.port,
    user: config.db.user,
    password: config.db.password,
    multipleStatements: true,
    charset: 'utf8mb4'
  });
  try {
    await connection.query(sql);
  } finally {
    await connection.end();
  }
}

export async function withTransaction(work) {
  const connection = await getPool().getConnection();
  try {
    await connection.beginTransaction();
    const result = await work(connection);
    await connection.commit();
    return result;
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}

export async function findSourceByName(name, connection = getPool()) {
  const [rows] = await connection.execute(
    'SELECT id_fuente, nombre FROM fuentes WHERE nombre = ? LIMIT 1',
    [name]
  );
  return rows[0] || null;
}

export async function createScan(sourceId, params) {
  const [result] = await getPool().execute(
    `INSERT INTO escaneos (id_fuente, estado, parametros, iniciado_en)
     VALUES (?, 'en_proceso', ?, NOW())`,
    [sourceId, JSON.stringify(params || {})]
  );
  return result.insertId;
}

export async function finishScan(scanId, summary) {
  await getPool().execute(
    `UPDATE escaneos
     SET estado = ?, total_encontradas = ?, total_guardadas = ?, total_descartadas = ?,
         total_errores = ?, mensaje_error = ?, finalizado_en = NOW()
     WHERE id_escaneo = ?`,
    [
      summary.totalErrores > 0 ? 'finalizado_con_errores' : 'finalizado',
      summary.totalEncontradas,
      summary.totalGuardadas,
      summary.totalDescartadas,
      summary.totalErrores,
      summary.mensajeError || null,
      scanId
    ]
  );
}

export async function failScan(scanId, error) {
  await getPool().execute(
    `UPDATE escaneos
     SET estado = 'fallido', total_errores = total_errores + 1,
         mensaje_error = ?, finalizado_en = NOW()
     WHERE id_escaneo = ?`,
    [String(error?.message || error).slice(0, 5000), scanId]
  );
}

export async function markInterruptedScans() {
  await getPool().execute(
    `UPDATE escaneos
     SET estado = 'cancelado',
         mensaje_error = 'Escaneo interrumpido por reinicio del bot',
         finalizado_en = NOW()
     WHERE estado IN ('iniciado', 'en_proceso')
       AND finalizado_en IS NULL`
  );
}

export async function insertScanResult({ scanId, publicationId, url, status, reason, extracted }) {
  await getPool().execute(
    `INSERT INTO resultados_escaneo
      (id_escaneo, id_publicacion, url_detectada, estado, motivo, datos_extraidos, fecha_registro)
     VALUES (?, ?, ?, ?, ?, ?, NOW())`,
    [
      scanId,
      publicationId || null,
      url,
      status,
      reason || null,
      extracted ? JSON.stringify(extracted).slice(0, 65000) : null
    ]
  );
}
