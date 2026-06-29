import { BaseSourceScraper } from './base.js';

export class FincaRaizScraper extends BaseSourceScraper {
  acceptsLink(href, text = '') {
    return super.acceptsLink(href, text)
      && /\/(casa|apartamento|inmueble|finca|lote)-?en-venta/i.test(href);
  }
}
