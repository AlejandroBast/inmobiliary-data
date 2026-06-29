import { BaseSourceScraper } from './base.js';
import { normalizeText } from '../services/parser.js';

export class AmorelScraper extends BaseSourceScraper {
  acceptsLink(href, text = '') {
    const normalized = normalizeText(`${href} ${text}`);
    if (!super.acceptsLink(href, text)) return false;
    return href.includes('/publicacion/')
      && (normalized.includes('vende')
      || normalized.includes('venta')
      || normalized.includes('vendo')
      || normalized.includes('apartamentos ventas')
      || normalized.includes('casas venta'));
  }
}
