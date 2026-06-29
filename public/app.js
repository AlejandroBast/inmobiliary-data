const rowsEl = document.querySelector('#rows');
const statusEl = document.querySelector('#status');
const fuenteInput = document.querySelector('#fuenteInput');
const barrioInput = document.querySelector('#barrioInput');
const searchInput = document.querySelector('#searchInput');
const refreshButton = document.querySelector('#refreshButton');
const startBotButton = document.querySelector('#startBotButton');
const runNowButton = document.querySelector('#runNowButton');
const stopBotButton = document.querySelector('#stopBotButton');
const botState = document.querySelector('#botState');
const botMeta = document.querySelector('#botMeta');
const detail = document.querySelector('#detail');
const detailContent = document.querySelector('#detailContent');
const closeDetail = document.querySelector('#closeDetail');

const money = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0
});

function setStatus(message) {
  statusEl.textContent = message;
}

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || response.statusText);
  }
  return response.json();
}

async function loadSources() {
  const sources = await api('/api/fuentes');
  for (const source of sources) {
    const option = document.createElement('option');
    option.value = source.nombre;
    option.textContent = source.nombre;
    fuenteInput.appendChild(option);
  }
}

async function loadRows() {
  setStatus('Cargando publicaciones...');
  const params = new URLSearchParams();
  if (fuenteInput.value) params.set('fuente', fuenteInput.value);
  if (barrioInput.value.trim()) params.set('barrio', barrioInput.value.trim());
  if (searchInput.value.trim()) params.set('q', searchInput.value.trim());
  const rows = await api(`/api/publicaciones?${params.toString()}`);
  rowsEl.innerHTML = '';
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><button class="secondary" data-id="${row.id}">${row.id}</button></td>
      <td>${escapeHtml(row.fecha || '')}</td>
      <td><span class="pill">${escapeHtml(row.fuente_origen || '')}</span></td>
      <td>${row.precio ? money.format(row.precio) : ''}</td>
      <td>${escapeHtml(row.barrio_o_ph || '')}</td>
      <td>${escapeHtml(row.tipo_inmueble || '')}</td>
      <td>${row.metros_cuadrados || ''}</td>
      <td>${row.valor_m2 ? money.format(row.valor_m2) : ''}</td>
      <td>${row.habitaciones || ''}</td>
      <td>${row.banos || ''}</td>
      <td>${row.total_imagenes}</td>
      <td>${row.total_anotaciones}</td>
      <td>${row.link_1 ? `<a class="link" target="_blank" rel="noreferrer" href="${row.link_1}">Abrir</a>` : ''}</td>
    `;
    tr.querySelector('button').addEventListener('click', () => openDetail(row.id));
    rowsEl.appendChild(tr);
  }
  setStatus(`${rows.length} publicaciones mostradas.`);
}

async function openDetail(id) {
  setStatus(`Cargando publicacion ${id}...`);
  const data = await api(`/api/publicaciones/${id}`);
  const p = data.publicacion;
  detailContent.innerHTML = `
    <h2>Publicacion ${p.id_publicacion}</h2>
    <p>${escapeHtml(p.fuente_origen || '')}</p>
    <p><strong>Precio:</strong> ${p.precio_normalizado ? money.format(p.precio_normalizado) : 'Sin precio'}</p>
    <p><strong>Tipo:</strong> ${escapeHtml(p.tipo_inmueble || '')}</p>
    <p><strong>Barrio:</strong> ${escapeHtml(p.barrio_texto || '')}</p>
    <p><strong>Descripcion:</strong></p>
    <p>${escapeHtml(p.descripcion_general || p.descripcion_original || '')}</p>
    <p>${p.enlace_publicacion ? `<a class="link" target="_blank" rel="noreferrer" href="${p.enlace_publicacion}">Abrir publicacion original</a>` : ''}</p>
    <h3>Imagenes</h3>
    <div class="gallery">
      ${data.imagenes.map((img) => `<img src="${toStorageUrl(img.ruta_archivo)}" alt="${escapeHtml(img.nombre_archivo || 'Imagen')}">`).join('')}
    </div>
    <h3>Anotaciones</h3>
    <div id="notes">
      ${data.anotaciones.map((note) => `<div class="note">${escapeHtml(note.texto)}</div>`).join('')}
    </div>
    <textarea id="newNote" placeholder="Nueva anotacion"></textarea>
    <button id="saveNote">Guardar anotacion</button>
  `;
  detail.classList.add('open');
  detailContent.querySelector('#saveNote').addEventListener('click', async () => {
    const text = detailContent.querySelector('#newNote').value.trim();
    if (!text) return;
    await api(`/api/publicaciones/${id}/anotaciones`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto: text })
    });
    await openDetail(id);
    await loadRows();
  });
  setStatus('Detalle cargado.');
}

function toStorageUrl(filePath) {
  if (!filePath) return '';
  const normalized = filePath.replaceAll('\\', '/');
  const marker = '/storage/';
  const index = normalized.lastIndexOf(marker);
  return index >= 0 ? normalized.slice(index) : '';
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }[char]));
}

refreshButton.addEventListener('click', () => loadRows().catch((error) => setStatus(error.message)));
fuenteInput.addEventListener('change', () => loadRows().catch((error) => setStatus(error.message)));
closeDetail.addEventListener('click', () => detail.classList.remove('open'));

startBotButton.addEventListener('click', async () => {
  setStatus('Iniciando bot automatico...');
  try {
    await api('/api/bot/start', { method: 'POST' });
    await loadBotStatus();
    setStatus('Bot automatico iniciado.');
  } catch (error) {
    setStatus(`Error iniciando bot: ${error.message}`);
  }
});

stopBotButton.addEventListener('click', async () => {
  setStatus('Deteniendo bot automatico...');
  try {
    await api('/api/bot/stop', { method: 'POST' });
    await loadBotStatus();
    setStatus('Bot automatico detenido.');
  } catch (error) {
    setStatus(`Error deteniendo bot: ${error.message}`);
  }
});

runNowButton.addEventListener('click', async () => {
  runNowButton.disabled = true;
  setStatus('Escaneo completo iniciado. El bot revisara todas las fuentes...');
  try {
    await api('/api/bot/run-now', { method: 'POST' });
    await loadBotStatus();
    setStatus('Escaneo completo iniciado en segundo plano.');
  } catch (error) {
    setStatus(`Error en escaneo: ${error.message}`);
  } finally {
    runNowButton.disabled = false;
  }
});

async function loadBotStatus() {
  const status = await api('/api/bot/status');
  botState.textContent = status.running
    ? 'escaneando ahora'
    : status.enabled
      ? 'activo y esperando'
      : 'detenido';
  const next = status.nextRunAt ? new Date(status.nextRunAt).toLocaleString('es-CO') : 'sin programar';
  const last = status.lastRunFinishedAt ? new Date(status.lastRunFinishedAt).toLocaleString('es-CO') : 'sin ejecuciones';
  const mode = status.scanMode?.unlimitedPages && status.scanMode?.unlimitedListings
    ? 'sin limite de paginas ni publicaciones'
    : 'con limite configurado';
  const totals = (status.lastSummaries || [])
    .map((summary) => `${summary.source}: ${summary.totalGuardadas} guardadas, ${summary.totalDescartadas} descartadas`)
    .join(' | ');
  botMeta.textContent = `Cada ${status.intervalMinutes} min | ${mode} | ultimo: ${last} | proximo: ${next}${totals ? ` | ${totals}` : ''}${status.lastError ? ` | error: ${status.lastError}` : ''}`;
}

loadSources()
  .then(loadRows)
  .then(loadBotStatus)
  .catch((error) => setStatus(error.message));

setInterval(() => {
  loadBotStatus().catch(() => {});
}, 5000);

setInterval(() => {
  loadRows().catch(() => {});
}, 60000);
