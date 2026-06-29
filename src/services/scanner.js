import { launchBrowser, newContext } from './browser.js';
import { createAllScrapers, createScraper } from '../sources/index.js';
import { createScan, failScan, findKnownUrls, findSourceByName, finishScan, insertScanResult } from '../db.js';
import { ingestListing, saveListingAssets } from './ingestor.js';
import { downloadAndOptimizeImages, saveEvidence } from './storage.js';
import { logger } from '../logger.js';
import { config } from '../config.js';

export async function scanSources({ sourceKeys = [], all = false, maxPages, maxListingsPerSource } = {}) {
  const scrapers = all || sourceKeys.length === 0
    ? createAllScrapers()
    : sourceKeys.map((key) => createScraper(key));
  const browser = await launchBrowser();
  const summaries = [];

  try {
    for (const scraper of scrapers) {
      const summary = await scanOneSource(browser, scraper, { maxPages, maxListingsPerSource });
      summaries.push(summary);
    }
  } finally {
    await browser.close();
  }

  return summaries;
}

async function scanOneSource(browser, scraper, options) {
  const source = await findSourceByName(scraper.definition.dbName);
  if (!source) throw new Error(`La fuente "${scraper.definition.dbName}" no existe. Ejecuta primero db:init.`);

  const scanId = await createScan(source.id_fuente, {
    source: scraper.definition.key,
    urls: scraper.definition.urls,
    maxPages: options.maxPages || config.bot.maxPages,
    maxListingsPerSource: options.maxListingsPerSource || config.bot.maxListingsPerSource,
    scanConcurrency: config.bot.scanConcurrency,
    skipKnownUrls: config.bot.skipKnownUrls
  });

  const summary = {
    source: scraper.definition.key,
    scanId,
    totalEncontradas: 0,
    totalGuardadas: 0,
    totalDescartadas: 0,
    totalOmitidas: 0,
    totalErrores: 0,
    mensajeError: null
  };

  const context = await newContext(browser, scraper.definition.key);
  try {
    const links = await scraper.discover(context, options);
    summary.totalEncontradas = links.length;
    logger.info({ source: scraper.definition.key, total: links.length }, 'Links detectados');

    const knownUrls = config.bot.skipKnownUrls
      ? await findKnownUrls(source.id_fuente, links.map((item) => item.href))
      : new Set();
    const linksToProcess = links.filter((item) => !knownUrls.has(item.href));
    summary.totalOmitidas = links.length - linksToProcess.length;

    if (summary.totalOmitidas > 0) {
      logger.info({
        source: scraper.definition.key,
        omitidas: summary.totalOmitidas,
        procesar: linksToProcess.length
      }, 'URLs ya conocidas omitidas');
    }

    await mapLimit(linksToProcess, config.bot.scanConcurrency, async (item) => {
      try {
        const listing = await scraper.extract(context, item);
        const saved = await ingestListing(listing);

        if (saved.status === 'descartado') {
          summary.totalDescartadas += 1;
          await insertScanResult({
            scanId,
            publicationId: null,
            url: item.href,
            status: 'descartado',
            reason: saved.reason,
            extracted: previewListing(listing)
          });
          return;
        }

        const evidences = await saveEvidence(saved.publicationId, listing);
        const images = await downloadAndOptimizeImages(saved.publicationId, listing.images);
        await saveListingAssets({
          publicationId: saved.publicationId,
          inmuebleId: saved.inmuebleId,
          evidences,
          images
        });

        summary.totalGuardadas += 1;
        await insertScanResult({
          scanId,
          publicationId: saved.publicationId,
          url: item.href,
          status: saved.status,
          reason: null,
          extracted: previewListing(listing)
        });
      } catch (error) {
        summary.totalErrores += 1;
        logger.error({ source: scraper.definition.key, url: item.href, error: error.message }, 'Error procesando publicacion');
        await insertScanResult({
          scanId,
          publicationId: null,
          url: item.href,
          status: 'error',
          reason: error.message,
          extracted: null
        });
      }
    });

    await finishScan(scanId, summary);
    return summary;
  } catch (error) {
    summary.totalErrores += 1;
    summary.mensajeError = error.message;
    await failScan(scanId, error);
    throw error;
  } finally {
    await context.close();
  }
}

async function mapLimit(items, limit, work) {
  const safeLimit = Math.max(1, Number.isFinite(limit) ? limit : 1);
  let index = 0;
  const workers = Array.from({ length: Math.min(safeLimit, items.length) }, async () => {
    while (index < items.length) {
      const currentIndex = index;
      index += 1;
      await work(items[currentIndex], currentIndex);
    }
  });
  await Promise.all(workers);
}

function previewListing(listing) {
  return {
    source: listing.sourceName,
    externalCode: listing.externalCode,
    title: listing.title,
    url: listing.url,
    price: listing.priceNormalized,
    barrio: listing.barrio,
    propertyType: listing.propertyType,
    area: listing.area,
    rooms: listing.rooms,
    baths: listing.baths,
    images: listing.images?.length || 0,
    discardReason: listing.discardReason || null
  };
}
