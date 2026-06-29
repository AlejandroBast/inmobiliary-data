import { BaseSourceScraper } from './base.js';

export class MetrocuadradoScraper extends BaseSourceScraper {
  acceptsLink(href, text = '') {
    return super.acceptsLink(href, text)
      && (/\/(apartamentos|casas|inmuebles)\/venta\//i.test(href) || /venta/i.test(text));
  }
}
