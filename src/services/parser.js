import crypto from 'node:crypto';

const rentWords = [
  'arriendo', 'arrienda', 'arrendar', 'arrendamiento', 'alquiler',
  'alquilo', 'renta', 'rentar'
];

const saleWords = [
  'venta', 'vende', 'vendo', 'vendemos', 'se vende', 'en venta',
  'comprar', 'oportunidad', 'inversion'
];

const knownBarrios = [
  'Centro', 'Palermo', 'Morasurco', 'Las Cuadras', 'La Colina', 'Torobajo',
  'San Ignacio', 'Lorenzo', 'El Ejido', 'Tamasagra', 'Agualongo', 'Capusigra',
  'Mariluz', 'Santa Isabel', 'Alfaguara', 'Invipaz', 'Obonuco', 'El Remolino',
  'Avenida Boyaca', 'San Felipe', 'Las Americas', 'La Castellana', 'Centenario',
  'El Bordo', 'Los Robles', 'Catambuco', 'Jardin', 'Alto Jardin', 'Pandiaco',
  'La Aurora', 'La Carolina', 'La Riviera', 'Chapal', 'Mijitayo', 'Miraflores',
  'Corazon de Jesus', 'Santa Monica', 'La Rosa', 'El Pilar', 'Anganoy',
  'San Fernando', 'San Luis', 'Venecia', 'Briceño', 'Briceno', 'Nueva Aranda',
  'El Tejar', 'Santa Ana', 'El Refugio', 'Maridiaz', 'Ciudad Real', 'Las Cuadras'
];

const outsidePastoPlaces = ['chachagui', 'ipiales', 'tuquerres', 'tumaco', 'popayan', 'cali', 'bogota'];

export function stripAccents(value = '') {
  return value.normalize('NFD').replace(/\p{Diacritic}/gu, '');
}

export function normalizeSpaces(value = '') {
  return value.replace(/\s+/g, ' ').trim();
}

export function normalizeText(value = '') {
  return normalizeSpaces(stripAccents(String(value)).toLowerCase());
}

export function sha256(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex');
}

export function isSaleText(text) {
  const normalized = normalizeText(text);
  const hasSale = saleWords.some((word) => normalized.includes(normalizeText(word)));
  const hasRent = rentWords.some((word) => normalized.includes(normalizeText(word)));
  return hasSale || !hasRent;
}

export function isPastoText(text) {
  const normalized = normalizeText(text);
  return normalized.includes('pasto') || normalized.includes('narino') || normalized.includes('nariño');
}

export function shouldDiscardByText(text) {
  const normalized = normalizeText(text);
  const hasSale = saleWords.some((word) => normalized.includes(normalizeText(word)));
  const hasRent = rentWords.some((word) => normalized.includes(normalizeText(word)));
  return hasRent && !hasSale;
}

export function isOutsidePastoText(text) {
  const normalized = normalizeText(text);
  return outsidePastoPlaces.some((place) => normalized.includes(place));
}

export function normalizePrice(text = '') {
  const lines = String(text)
    .split(/\n|(?<=\.)\s+/)
    .map((line) => normalizeSpaces(line))
    .filter(Boolean)
    .slice(0, 260);
  const priceCandidates = [];
  const moneyRegex = /(\$|cop|precio|valor)?\s*([0-9]{1,3}(?:[.,\s][0-9]{3})+|[0-9]+(?:[.,][0-9]+)?)(?:\s*(millones|millon|mm|m))?/gi;

  for (const line of lines) {
    const normalizedLine = normalizeText(line);
    const lineHasPriceMarker = /[$]|cop|precio|valor|compra|venta|vende|vendo|millones|millon|mm/.test(normalizedLine);
    if (!lineHasPriceMarker) continue;
    if (/administraci[oó]n|admin\b/.test(normalizedLine) && !/precio|valor de compra|venta/.test(normalizedLine)) continue;

    let match;
    moneyRegex.lastIndex = 0;
    while ((match = moneyRegex.exec(line)) !== null) {
      const prefix = normalizeText(match[1] || '');
      const rawNumber = match[2];
      const suffix = normalizeText(match[3] || '');
      const hasSeparator = /[.,\s]/.test(rawNumber);
      const after = normalizeText(line.slice(match.index + match[0].length, match.index + match[0].length + 24));
      const before = normalizeText(line.slice(Math.max(0, match.index - 16), match.index));
      if (suffix === 'm' && /^(2\b|inutos|inuto|etros|eses|es\b)/.test(after)) continue;
      if (/^(m2|m²|metros|habitaciones|habitacion|alcobas|alcoba|banos|baños|bano|baño|piso|garaje|minutos|minuto|horas|hora|meses|anos|años)/i.test(after)) continue;
      if (/(area|área|habitaciones|alcobas|banos|baños|piso|garaje|minutos|minuto|horas|hora|meses|anos|años)$/i.test(before)) continue;
      let value = parseMoneyNumber(rawNumber);
      if (!Number.isFinite(value)) continue;
      if (suffix || (value >= 20 && value <= 999 && (prefix || /precio|valor|compra|venta|vende|vendo/.test(normalizedLine)))) {
        value *= 1_000_000;
      } else if (!prefix && !suffix && !hasSeparator && value > 999) {
        continue;
      }
      if (value >= 10_000_000) {
        const score = (prefix ? 20 : 0) + (suffix ? 15 : 0) + (/precio|valor|compra/.test(normalizedLine) ? 20 : 0) - (/m2|metros|habitaciones|banos|baños/.test(normalizedLine) ? 10 : 0);
        priceCandidates.push({ original: match[0].trim(), value, score });
      }
    }
  }

  if (priceCandidates.length === 0) return { original: null, value: null, confidence: 0 };
  priceCandidates.sort((a, b) => b.score - a.score || b.value - a.value);
  return {
    original: priceCandidates[0].original,
    value: Math.round(priceCandidates[0].value),
    confidence: priceCandidates[0].value >= 30_000_000 ? 90 : 65
  };
}

function parseMoneyNumber(rawNumber) {
  const compact = rawNumber.trim();
  const thousandGroups = /^[0-9]{1,3}([.,\s][0-9]{3})+$/.test(compact);
  if (thousandGroups) {
    return Number(compact.replace(/[.,\s]/g, ''));
  }
  return Number(compact.replace(/\s/g, '').replace(',', '.'));
}

export function extractNumberByPatterns(text, patterns) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      const value = Number.parseFloat(match[1].replace(',', '.'));
      if (Number.isFinite(value)) return value;
    }
  }
  return null;
}

export function extractArea(text = '') {
  return extractNumberByPatterns(text, [
    /([0-9]+(?:[.,][0-9]+)?)\s*(?:m2|m²|mts2|metros cuadrados)/i,
    /area[^0-9]{0,15}([0-9]+(?:[.,][0-9]+)?)/i,
    /área[^0-9]{0,15}([0-9]+(?:[.,][0-9]+)?)/i
  ]);
}

export function extractBuiltArea(text = '') {
  return extractNumberByPatterns(text, [
    /construid[oa][^0-9]{0,15}([0-9]+(?:[.,][0-9]+)?)/i,
    /([0-9]+(?:[.,][0-9]+)?)\s*(?:m2|m²)\s*construid/i
  ]);
}

export function extractRooms(text = '') {
  return extractNumberByPatterns(text, [
    /([0-9]+)\s*(?:habitaciones|habitacion|alcobas|alcoba|hab\b)/i,
    /habitaciones?[^0-9]{0,10}([0-9]+)/i,
    /alcobas?[^0-9]{0,10}([0-9]+)/i
  ]);
}

export function extractBaths(text = '') {
  return extractNumberByPatterns(text, [
    /([0-9]+)\s*(?:banos|baños|bano|baño|bath)/i,
    /ba(?:n|ñ)os?[^0-9]{0,10}([0-9]+)/i
  ]);
}

export function extractParking(text = '') {
  const normalized = normalizeText(text);
  if (normalized.includes('sin parqueadero') || normalized.includes('no tiene parqueadero')) {
    return { has: false, detail: 'No' };
  }
  if (!normalized.includes('parqueadero') && !normalized.includes('garaje')) {
    return { has: null, detail: null };
  }
  const details = [];
  for (const word of ['privado', 'comunal', 'cubierto', 'descubierto', 'moto', 'doble']) {
    if (normalized.includes(word)) details.push(word);
  }
  return { has: true, detail: details.length ? details.join(', ') : 'Si' };
}

export function extractAdminFee(text = '') {
  const match = text.match(/admin(?:istraci[oó]n)?[^$0-9]{0,20}\$?\s*([0-9]{1,3}(?:[.,\s][0-9]{3})+|[0-9]+)/i);
  if (!match) return null;
  const value = Number(match[1].replace(/[.\s]/g, '').replace(',', '.'));
  return Number.isFinite(value) ? value : null;
}

export function extractFloor(text = '') {
  return extractNumberByPatterns(text, [
    /piso[^0-9]{0,10}([0-9]+)/i,
    /([0-9]+)\s*(?:er|do|to)?\s*piso/i
  ]);
}

export function extractPropertyType(text = '', url = '') {
  const normalizedUrl = normalizeText(url);
  if (/casa-en-venta|venta-casa/.test(normalizedUrl)) return 'casa';
  if (/apartamento-en-venta|venta-apartamento|apartaestudio/.test(normalizedUrl)) return 'apartamento';
  if (/lote-en-venta|venta-lote/.test(normalizedUrl)) return 'lote';
  if (/local-en-venta|venta-local/.test(normalizedUrl)) return 'local';
  if (/oficina-en-venta|venta-oficina/.test(normalizedUrl)) return 'oficina';
  if (/bodega-en-venta|venta-bodega/.test(normalizedUrl)) return 'bodega';
  if (/finca-en-venta|venta-finca/.test(normalizedUrl)) return 'finca';
  const normalized = normalizeText(`${text} ${url}`);
  if (normalized.includes('apartamento') || normalized.includes('apartaestudio')) return 'apartamento';
  if (normalized.includes('casa')) return 'casa';
  if (normalized.includes('lote')) return 'lote';
  if (normalized.includes('local')) return 'local';
  if (normalized.includes('oficina')) return 'oficina';
  if (normalized.includes('bodega')) return 'bodega';
  if (normalized.includes('finca')) return 'finca';
  return 'otro';
}

export function extractBarrio(text = '', url = '') {
  const urlBarrio = extractBarrioFromUrl(url);
  if (urlBarrio) return urlBarrio;
  const normalized = normalizeText(text);
  for (const barrio of knownBarrios) {
    if (normalized.includes(normalizeText(barrio))) return barrio;
  }
  const match = text.match(/barrio\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ0-9 ]{3,45})/i);
  if (!match) return null;
  const barrio = normalizeSpaces(match[1]).replace(/[.,;:|].*$/, '').trim();
  if (['comun', 'comun 1', 'comun 2', 'comuna', 'común'].includes(normalizeText(barrio))) return null;
  return barrio;
}

function extractBarrioFromUrl(url = '') {
  let decoded = '';
  try {
    decoded = decodeURIComponent(url);
  } catch {
    decoded = url;
  }
  const normalized = normalizeText(decoded);
  const patterns = [
    /en-venta-en-([a-z0-9-]+)-pasto/,
    /venta-[a-z]+-pasto-([a-z0-9-]+)/,
    /barrio%20([a-z0-9% -]+)/,
    /barrio\s+([a-z0-9 -]+)/
  ];
  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    if (!match) continue;
    const raw = match[1]
      .replace(/\/publicacion.*$/, '')
      .replace(/-[0-9].*$/, '')
      .replace(/\s+publicacion.*$/, '')
      .replace(/-/g, ' ');
    const words = raw.split(' ').filter((word) => !['br', 'co', 'et', 'ii'].includes(word));
    if (!words.length) continue;
    return titleCase(words.join(' '));
  }
  return null;
}

function titleCase(value) {
  return normalizeSpaces(value)
    .split(' ')
    .map((word) => word ? word[0].toUpperCase() + word.slice(1).toLowerCase() : '')
    .join(' ');
}

export function extractExternalCode(url = '', text = '') {
  const numericTail = url.match(/(?:-|\/)([0-9]{5,})(?:[/?#]|$)/);
  if (numericTail) return numericTail[1];

  const fse = text.match(/\bFSE\s*([0-9-]+)/i);
  if (fse) return `FSE-${fse[1]}`;
  const code = text.match(/\b(?:codigo|c[oó]digo|cod)\s*[:#]?\s*([A-Z0-9-]{4,})/i);
  if (code && /[0-9]/.test(code[1])) return code[1];
  return sha256(url).slice(0, 24);
}

export function buildListingFromText({ sourceKey, sourceName, url, title, bodyText, html, images, sellerProfileUrl, screenshot }) {
  const combined = normalizeSpaces([title, bodyText].filter(Boolean).join('\n'));
  const scopeText = normalizeSpaces([title, url, bodyText?.slice(0, 1200)].filter(Boolean).join('\n'));
  const price = normalizePrice([title, bodyText].filter(Boolean).join('\n'));
  const propertyType = extractPropertyType(combined, url);
  const area = extractArea(combined);
  const builtArea = extractBuiltArea(combined);
  const parking = extractParking(combined);
  const barrio = extractBarrio(combined, url);
  const externalCode = extractExternalCode(url, combined);
  const description = normalizeSpaces(bodyText || title || '').slice(0, 6000);
  const confidencePieces = [
    price.value,
    barrio,
    area,
    extractRooms(combined),
    extractBaths(combined),
    description.length > 30,
    images?.length
  ].filter(Boolean).length;

  return {
    sourceKey,
    sourceName,
    externalCode,
    url,
    title: normalizeSpaces(title || '').slice(0, 340),
    sellerProfileUrl: sellerProfileUrl || null,
    capturedAt: new Date(),
    rawText: bodyText || '',
    rawHtml: html || '',
    screenshot: screenshot || null,
    priceOriginal: price.original,
    priceNormalized: price.value,
    priceConfidence: price.confidence,
    propertyType,
    concept: propertyType === 'otro' ? 'Venta de inmueble' : `Venta de ${propertyType}`,
    city: 'Pasto',
    department: 'Narino',
    barrio,
    locationText: barrio ? `${barrio}, Pasto, Narino` : 'Pasto, Narino',
    description,
    area,
    builtArea,
    rooms: extractRooms(combined),
    baths: extractBaths(combined),
    parking: parking.has,
    parkingDetail: parking.detail,
    floorApartment: propertyType === 'apartamento' ? extractFloor(combined) : null,
    houseFloors: propertyType === 'casa' ? extractFloor(combined) : null,
    adminFee: extractAdminFee(combined),
    images: images || [],
    confidence: Math.min(100, 40 + confidencePieces * 8),
    contentHash: sha256(`${sourceName}|${externalCode}|${url}`),
    validationWarnings: buildValidationWarnings({ price, barrio, description, propertyType }),
    discardReason: buildDiscardReason({ combined, scopeText, price, barrio, description, externalCode, propertyType, url })
  };
}

function buildValidationWarnings({ price, barrio, description, propertyType }) {
  const warnings = [];
  if (propertyType === 'otro') warnings.push('Sin tipo de inmueble claro');
  if (!price.value) warnings.push('Sin precio valido');
  if (!barrio) warnings.push('Sin barrio o sector claro');
  if (!description || description.length < 20) warnings.push('Sin descripcion suficiente');
  return warnings;
}

function buildDiscardReason({ combined, scopeText, price, barrio, description, externalCode, propertyType, url }) {
  if (!url) return 'Sin link de origen';
  if (isOutsidePastoText(scopeText)) return 'Ubicacion fuera de Pasto';
  if (!isPastoText(scopeText)) return 'No se pudo confirmar Pasto/Narino';
  if (shouldDiscardByText(combined)) return 'Publicacion de arriendo, no venta';
  return null;
}
