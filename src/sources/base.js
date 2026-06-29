import { config } from '../config.js';
import { logger } from '../logger.js';
import { buildListingFromText, normalizeText, shouldDiscardByText } from '../services/parser.js';
import { politeDelay } from '../services/browser.js';

export class BaseSourceScraper {
  constructor(definition) {
    this.definition = definition;
  }

  async discover(context, options = {}) {
    const page = await context.newPage();
    const links = new Map();
    const maxPages = options.maxPages ?? config.bot.maxPages;
    const maxListings = options.maxListingsPerSource ?? config.bot.maxListingsPerSource;
    const unlimitedPages = maxPages <= 0;
    const unlimitedListings = maxListings <= 0;
    const hardPageLimit = 500;

    try {
      for (const startUrl of this.definition.urls) {
        let currentUrl = startUrl;
        const visitedPages = new Set();
        for (let pageNumber = 1; currentUrl; pageNumber += 1) {
          if (!unlimitedPages && pageNumber > maxPages) break;
          if (pageNumber > hardPageLimit) break;
          if (visitedPages.has(currentUrl)) break;
          visitedPages.add(currentUrl);
          logger.info({ source: this.definition.key, url: currentUrl }, 'Visitando pagina de resultados');
          await page.goto(currentUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
          await this.afterResultsLoaded(page);
          const pageLinks = await this.extractCandidateLinks(page);
          for (const item of pageLinks) {
            if (this.acceptsLink(item.href, item.text)) {
              links.set(item.href, item);
            }
            if (!unlimitedListings && links.size >= maxListings) break;
          }
          if (!unlimitedListings && links.size >= maxListings) break;
          currentUrl = await this.findNextUrl(page, currentUrl);
          await politeDelay();
        }
        if (!unlimitedListings && links.size >= maxListings) break;
      }
    } finally {
      await page.close();
    }

    const discovered = [...links.values()];
    return unlimitedListings ? discovered : discovered.slice(0, maxListings);
  }

  async extract(context, item) {
    const page = await context.newPage();
    try {
      logger.info({ source: this.definition.key, url: item.href }, 'Extrayendo publicacion');
      await page.goto(item.href, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await this.afterDetailLoaded(page);
      const title = await page.title().catch(() => item.text || '');
      const bodyText = await page.locator('body').innerText({ timeout: 15000 }).catch(() => item.text || '');
      const html = config.bot.saveEvidence ? await page.content().catch(() => '') : '';
      const images = await this.extractImages(page);
      const sellerProfileUrl = await this.extractSellerProfile(page);
      const screenshot = config.bot.saveEvidence && config.bot.saveScreenshots
        ? await page.screenshot({ fullPage: true }).catch(() => null)
        : null;

      return buildListingFromText({
        sourceKey: this.definition.key,
        sourceName: this.definition.dbName,
        url: item.href,
        title,
        bodyText,
        html,
        images,
        sellerProfileUrl,
        screenshot
      });
    } finally {
      await page.close();
    }
  }

  async afterResultsLoaded(page) {
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    await autoScroll(page);
  }

  async afterDetailLoaded(page) {
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  }

  async extractCandidateLinks(page) {
    return page.$$eval('a', (anchors) => anchors
      .map((anchor) => ({
        href: anchor.href,
        text: (anchor.innerText || anchor.textContent || '').trim()
      }))
      .filter((item) => item.href));
  }

  acceptsLink(href, text = '') {
    let parsed;
    try {
      parsed = new URL(href);
    } catch {
      return false;
    }
    if (!this.definition.allowedHosts.includes(parsed.host)) return false;
    const combined = normalizeText(`${href} ${text}`);
    if (shouldDiscardByText(combined)) return false;
    if (this.definition.requireRegionalUrl) {
      const normalizedHref = normalizeText(href);
      const regionHints = this.definition.regionHints || [];
      if (!regionHints.some((hint) => normalizedHref.includes(normalizeText(hint)))) {
        return false;
      }
    }
    return this.definition.linkHints.some((hint) => combined.includes(normalizeText(hint)));
  }

  async findNextUrl(page, currentUrl) {
    const candidates = await page.$$eval('a', (anchors) => anchors
      .map((anchor) => ({
        href: anchor.href,
        rel: anchor.getAttribute('rel') || '',
        text: (anchor.innerText || anchor.getAttribute('aria-label') || '').trim()
      }))
      .filter((item) => item.href));

    const next = candidates.find((item) => {
      const label = `${item.rel} ${item.text}`.toLowerCase();
      return label.includes('next') || label.includes('siguiente') || label === '>';
    });
    if (!next || next.href === currentUrl) return null;
    return next.href;
  }

  async extractImages(page) {
    const images = await page.$$eval('img', (nodes) => nodes
      .map((img) => ({
        url: img.currentSrc || img.src || '',
        alt: img.alt || '',
        width: img.naturalWidth || 0,
        height: img.naturalHeight || 0
      }))
      .filter((img) => img.url && !img.url.startsWith('data:')));

    const seen = new Set();
    return images
      .filter((img) => {
        if (seen.has(img.url)) return false;
        seen.add(img.url);
        return img.width >= 180 || img.height >= 180 || img.url.includes('image');
      })
      .slice(0, 20);
  }

  async extractSellerProfile(page) {
    const links = await page.$$eval('a', (anchors) => anchors
      .map((anchor) => ({
        href: anchor.href,
        text: (anchor.innerText || '').trim()
      }))
      .filter((item) => item.href));
    const profile = links.find((item) => /facebook\.com\/(profile|people|marketplace\/profile)/i.test(item.href));
    return profile?.href || null;
  }
}

async function autoScroll(page) {
  await page.evaluate(async () => {
    await new Promise((resolve) => {
      let totalHeight = 0;
      const distance = 700;
      const timer = setInterval(() => {
        window.scrollBy(0, distance);
        totalHeight += distance;
        if (totalHeight >= Math.min(document.body.scrollHeight, 5000)) {
          clearInterval(timer);
          resolve();
        }
      }, 180);
    });
  }).catch(() => {});
}
