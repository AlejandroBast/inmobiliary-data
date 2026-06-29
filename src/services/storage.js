import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import sharp from 'sharp';
import { config } from '../config.js';
import { logger } from '../logger.js';

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

function sha256Buffer(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

export async function saveEvidence(publicationId, listing) {
  if (!config.bot.saveEvidence) return [];
  const evidenceDir = path.join(config.bot.storageDir, 'evidencias', `publicacion_${publicationId}`);
  await ensureDir(evidenceDir);
  const saved = [];

  if (listing.rawHtml) {
    const htmlPath = path.join(evidenceDir, `publicacion_${publicationId}.html`);
    await fs.writeFile(htmlPath, listing.rawHtml, 'utf8');
    saved.push({
      type: 'html',
      path: htmlPath,
      description: 'HTML capturado de la publicacion',
      hash: crypto.createHash('sha256').update(listing.rawHtml).digest('hex')
    });
  }

  if (listing.screenshot) {
    const screenshotPath = path.join(evidenceDir, `publicacion_${publicationId}_captura.png`);
    await fs.writeFile(screenshotPath, listing.screenshot);
    saved.push({
      type: 'captura',
      path: screenshotPath,
      description: 'Captura de pantalla de la publicacion',
      hash: sha256Buffer(listing.screenshot)
    });
  }

  return saved;
}

export async function downloadAndOptimizeImages(publicationId, images) {
  if (!config.bot.downloadImages || !images?.length) return [];
  const imageDir = path.join(config.bot.storageDir, 'imagenes', `publicacion_${publicationId}`);
  await ensureDir(imageDir);
  const saved = [];

  for (const [index, image] of images.entries()) {
    try {
      const response = await fetch(image.url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari'
        }
      });
      if (!response.ok) continue;
      const input = Buffer.from(await response.arrayBuffer());
      const originalHash = sha256Buffer(input);
      const fileName = `publicacion_${String(publicationId).padStart(6, '0')}_imagen_${String(index + 1).padStart(2, '0')}.webp`;
      const outputPath = path.join(imageDir, fileName);
      const pipeline = sharp(input).rotate().resize({
        width: 1600,
        height: 1600,
        fit: 'inside',
        withoutEnlargement: true
      }).webp({ quality: 78 });
      await pipeline.toFile(outputPath);
      const metadata = await sharp(outputPath).metadata();
      const stat = await fs.stat(outputPath);

      saved.push({
        urlOriginal: image.url,
        path: outputPath,
        fileName,
        order: index + 1,
        hash: originalHash,
        format: 'webp',
        weightKb: Math.round((stat.size / 1024) * 100) / 100,
        width: metadata.width || null,
        height: metadata.height || null,
        isCover: index === 0
      });
    } catch (error) {
      logger.warn({ image: image.url, error: error.message }, 'No se pudo descargar/optimizar imagen');
    }
  }

  return saved;
}
