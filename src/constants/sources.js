import { config } from '../config.js';

const sourceDefinitions = {
  fincaraiz: {
    key: 'fincaraiz',
    dbName: 'FincaRaiz',
    baseUrl: 'https://www.fincaraiz.com.co/',
    urls: [
      'https://www.fincaraiz.com.co/venta/casas-y-apartamentos/pasto/narino',
      'https://www.fincaraiz.com.co/venta/apartamentos/pasto/narino',
      'https://www.fincaraiz.com.co/venta/casas/pasto/narino'
    ],
    allowedHosts: ['www.fincaraiz.com.co', 'fincaraiz.com.co'],
    linkHints: ['venta', 'pasto']
  },
  metrocuadrado: {
    key: 'metrocuadrado',
    dbName: 'Metrocuadrado',
    baseUrl: 'https://www.metrocuadrado.com/',
    urls: [
      'https://www.metrocuadrado.com/inmuebles/venta/pasto/',
      'https://www.metrocuadrado.com/apartamentos/venta/pasto/',
      'https://www.metrocuadrado.com/casas/venta/pasto/'
    ],
    allowedHosts: ['www.metrocuadrado.com', 'metrocuadrado.com'],
    linkHints: ['venta', 'pasto']
  },
  ciencuadras: {
    key: 'ciencuadras',
    dbName: 'Ciencuadras',
    baseUrl: 'https://www.ciencuadras.com/',
    urls: [
      'https://www.ciencuadras.com/venta/pasto',
      'https://www.ciencuadras.com/venta/pasto/apartamento',
      'https://www.ciencuadras.com/venta/pasto/casa-apartamento'
    ],
    allowedHosts: ['www.ciencuadras.com', 'ciencuadras.com'],
    linkHints: ['venta', 'pasto']
  },
  amorel: {
    key: 'amorel',
    dbName: 'Clasificados Amorel',
    baseUrl: 'https://amorelpasto.com/clasificados/web/app.php/resultados/Finca%20Raiz',
    urls: [
      'https://amorelpasto.com/clasificados/web/app.php/resultados/Finca%20Raiz',
      'https://amorelpasto.com/clasificados/web/app.php/resultados/Finca%20Raiz/casas%20venta',
      'https://amorelpasto.com/clasificados/web/app.php/resultados/Finca%20Raiz/apartamentos%20ventas'
    ],
    allowedHosts: ['amorelpasto.com', 'www.amorelpasto.com'],
    linkHints: ['finca', 'raiz', 'venta', 'vende', 'vendo']
  },
  facebook: {
    key: 'facebook',
    dbName: 'Facebook Marketplace',
    baseUrl: 'https://www.facebook.com/marketplace/',
    urls: [
      'https://www.facebook.com/marketplace/search?query=apartamento%20venta%20pasto',
      'https://www.facebook.com/marketplace/search?query=casa%20venta%20pasto',
      'https://www.facebook.com/marketplace/search?query=inmueble%20venta%20pasto'
    ],
    allowedHosts: ['www.facebook.com', 'facebook.com', 'm.facebook.com'],
    linkHints: ['marketplace', 'item']
  }
};

export function getSourceDefinition(key) {
  const definition = sourceDefinitions[key];
  if (!definition) return null;
  return {
    ...definition,
    urls: config.urlOverrides[key] || definition.urls
  };
}

export function getAllSourceDefinitions() {
  return Object.keys(sourceDefinitions).map(getSourceDefinition);
}
