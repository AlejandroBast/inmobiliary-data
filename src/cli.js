import { Command } from 'commander';
import { initDatabase, closePool } from './db.js';
import { scanSources } from './services/scanner.js';
import { scannerDaemon } from './services/daemon.js';
import { listSourceKeys } from './sources/index.js';
import { logger } from './logger.js';

const program = new Command();

program
  .name('inmobiliary-bot')
  .description('Bot de scraping para Inmobiliary-Data')
  .version('1.0.0');

program
  .command('db:init')
  .description('Crea/actualiza la base de datos usando inmobiliary_db.sql')
  .action(async () => {
    await initDatabase();
    logger.info('Base de datos inicializada.');
    await closePool();
  });

program
  .command('scan')
  .description('Escanea fuentes autorizadas')
  .option('--all', 'Escanear todas las fuentes')
  .option('--source <source>', `Fuente: ${listSourceKeys().join(', ')}`)
  .option('--max-pages <number>', 'Maximo de paginas por fuente', Number.parseInt)
  .option('--max-listings <number>', 'Maximo de publicaciones por fuente', Number.parseInt)
  .action(async (options) => {
    const sourceKeys = options.source ? [options.source] : [];
    const summaries = await scanSources({
      all: Boolean(options.all) || sourceKeys.length === 0,
      sourceKeys,
      maxPages: options.maxPages,
      maxListingsPerSource: options.maxListings
    });
    console.table(summaries);
    await closePool();
  });

program
  .command('daemon')
  .description('Mantiene el bot escaneando automaticamente todas las fuentes')
  .action(async () => {
    scannerDaemon.start({ runImmediately: true });
    logger.info('Daemon activo. Usa Ctrl+C para detenerlo.');
  });

program.parseAsync().catch(async (error) => {
  logger.error(error);
  await closePool();
  process.exit(1);
});
