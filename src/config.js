import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
dotenv.config({ path: process.env.ENV_FILE || path.join(projectRoot, '.env') });

function boolEnv(name, fallback) {
  const value = process.env[name];
  if (value === undefined || value === '') return fallback;
  return ['1', 'true', 'yes', 'si', 'on'].includes(value.toLowerCase());
}

function intEnv(name, fallback) {
  const value = Number.parseInt(process.env[name] || '', 10);
  return Number.isFinite(value) ? value : fallback;
}

function csvEnv(name, fallback) {
  const raw = process.env[name];
  if (!raw) return fallback;
  return raw.split(',').map((item) => item.trim()).filter(Boolean);
}

export const config = {
  projectRoot,
  schemaPath: path.resolve(projectRoot, '..', 'inmobiliary_db.sql'),
  db: {
    host: process.env.DB_HOST || '127.0.0.1',
    port: intEnv('DB_PORT', 3306),
    user: process.env.DB_USER || 'root',
    password: process.env.DB_PASSWORD || '',
    database: process.env.DB_NAME || 'inmobiliary_data',
    waitForConnections: true,
    connectionLimit: intEnv('DB_POOL_LIMIT', 10),
    multipleStatements: false,
    charset: 'utf8mb4'
  },
  bot: {
    headless: boolEnv('BOT_HEADLESS', true),
    maxPages: intEnv('BOT_MAX_PAGES', 3),
    maxListingsPerSource: intEnv('BOT_MAX_LISTINGS_PER_SOURCE', 30),
    autoScan: boolEnv('BOT_AUTO_SCAN', false),
    scanOnStart: boolEnv('BOT_SCAN_ON_START', true),
    scanIntervalMinutes: intEnv('BOT_SCAN_INTERVAL_MINUTES', 30),
    delayMs: intEnv('BOT_DELAY_MS', 1500),
    city: process.env.BOT_CITY || 'Pasto',
    department: process.env.BOT_DEPARTMENT || 'Narino',
    storageDir: path.resolve(projectRoot, process.env.BOT_STORAGE_DIR || './storage'),
    downloadImages: boolEnv('BOT_DOWNLOAD_IMAGES', true),
    saveEvidence: boolEnv('BOT_SAVE_EVIDENCE', true),
    saveScreenshots: boolEnv('BOT_SAVE_SCREENSHOTS', true)
  },
  web: {
    host: process.env.WEB_HOST || '127.0.0.1',
    port: intEnv('WEB_PORT', 3000)
  },
  facebookStorageState: process.env.FACEBOOK_STORAGE_STATE || '',
  urlOverrides: {
    fincaraiz: csvEnv('FINCARAIZ_URLS', null),
    metrocuadrado: csvEnv('METROCUADRADO_URLS', null),
    ciencuadras: csvEnv('CIENCUADRAS_URLS', null),
    amorel: csvEnv('AMOREL_URLS', null),
    facebook: csvEnv('FACEBOOK_URLS', null)
  }
};
