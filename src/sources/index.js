import { getAllSourceDefinitions, getSourceDefinition } from '../constants/sources.js';
import { FincaRaizScraper } from './fincaraiz.js';
import { MetrocuadradoScraper } from './metrocuadrado.js';
import { CiencuadrasScraper } from './ciencuadras.js';
import { AmorelScraper } from './amorel.js';
import { FacebookScraper } from './facebook.js';

const scraperClasses = {
  fincaraiz: FincaRaizScraper,
  metrocuadrado: MetrocuadradoScraper,
  ciencuadras: CiencuadrasScraper,
  amorel: AmorelScraper,
  facebook: FacebookScraper
};

export function createScraper(key) {
  const definition = getSourceDefinition(key);
  if (!definition) throw new Error(`Fuente no soportada: ${key}`);
  const Scraper = scraperClasses[key];
  return new Scraper(definition);
}

export function createAllScrapers() {
  return getAllSourceDefinitions().map((definition) => {
    const Scraper = scraperClasses[definition.key];
    return new Scraper(definition);
  });
}

export function listSourceKeys() {
  return getAllSourceDefinitions().map((definition) => definition.key);
}
