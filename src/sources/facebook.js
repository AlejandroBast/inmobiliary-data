import { BaseSourceScraper } from './base.js';

export class FacebookScraper extends BaseSourceScraper {
  acceptsLink(href, text = '') {
    const propertyText = /casa|apartamento|apartaestudio|inmueble|vivienda|lote|venta|vende|vendo/i.test(text);
    return super.acceptsLink(href, text)
      && /marketplace\/item/i.test(href)
      && propertyText;
  }

  async extractSellerProfile(page) {
    const links = await page.$$eval('a', (anchors) => anchors
      .map((anchor) => ({
        href: anchor.href,
        text: (anchor.innerText || '').trim()
      }))
      .filter((item) => item.href));
    const profile = links.find((item) => /facebook\.com\/(marketplace\/profile|profile\.php|people\/|[A-Za-z0-9.]+\/?$)/i.test(item.href));
    return profile?.href || null;
  }
}
