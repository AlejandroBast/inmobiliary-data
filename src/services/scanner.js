import { launchBrowser, newContext } from './browser.js';
import { createAllScrapers, createScraper } from '../sources/index.js';
import { createScan, failScan, findSourceByName, finishScan, insertScanResult } from '../db.js';
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
    maxListingsPerSource: options.maxListingsPerSource || config.bot.maxListingsPerSource
  });

  const summary = {
    source: scraper.definition.key,
    scanId,
    totalEncontradas: 0,
    totalGuardadas: 0,
    totalDescartadas: 0,
    totalErrores: 0,
    mensajeError: null
  };

  const context = await newContext(browser, scraper.definition.key);
  try {
    const links = await scraper.discover(context, options);
    summary.totalEncontradas = links.length;
    logger.info({ source: scraper.definition.key, total: links.length }, 'Links detectados');

    for (const item of links) {
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
          continue;
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
    }

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
