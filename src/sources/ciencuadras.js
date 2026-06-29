import { BaseSourceScraper } from './base.js';

export class CiencuadrasScraper extends BaseSourceScraper {
  acceptsLink(href, text = '') {
    return super.acceptsLink(href, text)
      && /\/inmueble\//i.test(href)
      && /en-venta/i.test(href)
      && /pasto/i.test(href + text);
  }
}
