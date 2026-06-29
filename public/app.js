const rowsEl = document.querySelector('#rows');
const statusEl = document.querySelector('#status');
const fuenteInput = document.querySelector('#fuenteInput');
const barrioInput = document.querySelector('#barrioInput');
const searchInput = document.querySelector('#searchInput');
const refreshButton = document.querySelector('#refreshButton');
const createButton = document.querySelector('#createButton');
const startBotButton = document.querySelector('#startBotButton');
const runNowButton = document.querySelector('#runNowButton');
const stopBotButton = document.querySelector('#stopBotButton');
const botState = document.querySelector('#botState');
const botMeta = document.querySelector('#botMeta');
const detail = document.querySelector('#detail');
const detailContent = document.querySelector('#detailContent');
const closeDetail = document.querySelector('#closeDetail');
let currentImages = [];
let currentImageIndex = 0;

const money = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0
});

let sourceOptions = [];

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
  sourceOptions = sources;
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
      <td><button class="id-button secondary" data-id="${row.id}">${row.id}</button></td>
      <td>${escapeHtml(row.fecha || '')}</td>
      <td><span class="pill">${escapeHtml(row.fuente_origen || '')}</span></td>
      <td class="num">${row.precio ? money.format(row.precio) : ''}</td>
      <td>${escapeHtml(row.barrio_o_ph || '')}</td>
      <td>${escapeHtml(row.tipo_inmueble || '')}</td>
      <td class="num">${row.metros_cuadrados || ''}</td>
      <td class="num">${row.valor_m2 ? money.format(row.valor_m2) : ''}</td>
      <td class="num">${row.habitaciones || ''}</td>
      <td class="num">${row.banos || ''}</td>
      <td class="num">${row.total_imagenes}</td>
      <td class="num">${row.total_anotaciones}</td>
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
  const description = p.descripcion_general || p.descripcion_original || '';
  detailContent.innerHTML = `
    <div class="detail-header">
      <div>
        <h2>Publicacion ${p.id_publicacion}</h2>
        <span class="pill">${escapeHtml(p.fuente_origen || '')}</span>
      </div>
      <div class="detail-actions">
        ${p.enlace_publicacion ? `<a class="button-link" target="_blank" rel="noreferrer" href="${p.enlace_publicacion}">Abrir original</a>` : ''}
        <button id="editPublication" class="secondary">Editar</button>
        <button id="deletePublication" class="danger">Eliminar</button>
      </div>
    </div>

    <div class="detail-fields">
      ${detailField('Precio', p.precio_normalizado ? money.format(p.precio_normalizado) : 'Sin precio')}
      ${detailField('Tipo', p.tipo_inmueble)}
      ${detailField('Barrio', p.barrio_texto || p.localizacion_texto)}
      ${detailField('m2', p.m2)}
      ${detailField('Hab.', p.habitaciones)}
      ${detailField('Banos', p.banos)}
      ${detailField('Parqueadero', p.parqueadero_detalle || formatBoolean(p.parqueadero))}
      ${detailField('Administracion', p.valor_administracion ? money.format(p.valor_administracion) : '')}
    </div>

    <section class="detail-section">
      <h3>Descripcion</h3>
      <p class="description">${escapeHtml(description || 'Sin descripcion disponible.')}</p>
    </section>

    <section class="detail-section">
      <h3>Imagenes <span>${data.imagenes.length}</span></h3>
      <div class="gallery">
        ${data.imagenes.map((img, index) => `
          <button class="image-thumb" type="button" data-index="${index}" aria-label="Ver imagen ${index + 1}">
            <img src="${toStorageUrl(img.ruta_archivo)}" alt="${escapeHtml(img.nombre_archivo || 'Imagen')}">
          </button>
        `).join('')}
      </div>
    </section>

    <section class="detail-section">
      <h3>Anotaciones</h3>
      <div id="notes">
        ${data.anotaciones.map((note) => `<div class="note">${escapeHtml(note.texto)}</div>`).join('')}
      </div>
      <textarea id="newNote" placeholder="Nueva anotacion"></textarea>
      <button id="saveNote">Guardar anotacion</button>
    </section>
  `;
  detail.classList.add('open');
  document.body.classList.add('detail-open');
  currentImages = data.imagenes.map((img) => ({
    src: toStorageUrl(img.ruta_archivo),
    alt: img.nombre_archivo || 'Imagen'
  })).filter((img) => img.src);
  detailContent.querySelectorAll('.image-thumb').forEach((button) => {
    button.addEventListener('click', () => openImageViewer(Number(button.dataset.index || 0)));
  });
  detailContent.querySelector('#editPublication').addEventListener('click', () => openPublicationForm('edit', p));
  detailContent.querySelector('#deletePublication').addEventListener('click', () => deletePublication(p.id_publicacion));
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

function openPublicationForm(mode, publication = {}) {
  const isEdit = mode === 'edit';
  const selectedSource = publication.publicacion_id_fuente || publication.id_fuente || '';
  detailContent.innerHTML = `
    <div class="detail-header">
      <div>
        <h2>${isEdit ? `Editar publicacion ${publication.id_publicacion}` : 'Nueva publicacion'}</h2>
        <p>${isEdit ? 'Actualiza los datos principales.' : 'Registra una publicacion manual.'}</p>
      </div>
    </div>

    <form id="publicationForm" class="crud-form">
      <label>
        Fuente
        <select name="id_fuente" required>
          <option value="">Selecciona una fuente</option>
          ${sourceOptions.map((source) => `
            <option value="${source.id_fuente}" ${String(source.id_fuente) === String(selectedSource) ? 'selected' : ''}>${escapeHtml(source.nombre)}</option>
          `).join('')}
        </select>
      </label>

      <label>
        Titulo
        <input name="titulo" maxlength="350" value="${escapeAttribute(publication.titulo || '')}" placeholder="Casa en venta...">
      </label>

      <label class="wide">
        Link
        <input name="enlace_publicacion" required value="${escapeAttribute(publication.enlace_publicacion || '')}" placeholder="https://...">
      </label>

      <label>
        Codigo fuente
        <input name="codigo_publicacion_fuente" value="${escapeAttribute(publication.codigo_publicacion_fuente || '')}" placeholder="Opcional">
      </label>

      <label>
        Estado
        <select name="estado_publicacion">
          ${['activa', 'inactiva', 'pausada', 'vendida', 'descartada', 'error', 'desconocida'].map((estado) => `
            <option value="${estado}" ${estado === (publication.estado_publicacion || 'activa') ? 'selected' : ''}>${estado}</option>
          `).join('')}
        </select>
      </label>

      <label>
        Tipo
        <select name="tipo_inmueble">
          ${['apartamento', 'casa', 'lote', 'local', 'oficina', 'bodega', 'finca', 'otro'].map((tipo) => `
            <option value="${tipo}" ${tipo === (publication.tipo_inmueble || 'apartamento') ? 'selected' : ''}>${tipo}</option>
          `).join('')}
        </select>
      </label>

      <label>
        Barrio
        <input name="barrio_texto" value="${escapeAttribute(publication.barrio_texto || '')}" placeholder="Centro">
      </label>

      <label>
        Precio
        <input name="precio_normalizado" type="number" min="0" step="1000" value="${publication.precio_normalizado || ''}">
      </label>

      <label>
        m2
        <input name="m2" type="number" min="0" step="0.01" value="${publication.m2 || ''}">
      </label>

      <label>
        Habitaciones
        <input name="habitaciones" type="number" min="0" step="1" value="${publication.habitaciones || ''}">
      </label>

      <label>
        Banos
        <input name="banos" type="number" min="0" step="1" value="${publication.banos || ''}">
      </label>

      <label>
        Administracion
        <input name="valor_administracion" type="number" min="0" step="1000" value="${publication.valor_administracion || ''}">
      </label>

      <label class="wide">
        Descripcion
        <textarea name="descripcion">${escapeHtml(publication.descripcion_general || publication.descripcion_original || '')}</textarea>
      </label>

      <div class="form-actions wide">
        <button type="submit">${isEdit ? 'Guardar cambios' : 'Crear publicacion'}</button>
        <button type="button" class="secondary" id="cancelForm">Cancelar</button>
      </div>
    </form>
  `;
  detail.classList.add('open');
  document.body.classList.add('detail-open');

  detailContent.querySelector('#cancelForm').addEventListener('click', () => {
    if (isEdit) openDetail(publication.id_publicacion);
    else closeDetailPanel();
  });
  detailContent.querySelector('#publicationForm').addEventListener('submit', (event) => {
    event.preventDefault();
    savePublication(mode, publication.id_publicacion, event.currentTarget).catch((error) => setStatus(error.message));
  });
}

async function savePublication(mode, id, form) {
  const payload = Object.fromEntries(new FormData(form).entries());
  for (const key of ['id_fuente', 'precio_normalizado', 'm2', 'habitaciones', 'banos', 'valor_administracion']) {
    payload[key] = payload[key] === '' ? null : Number(payload[key]);
  }
  const path = mode === 'edit' ? `/api/publicaciones/${id}` : '/api/publicaciones';
  const method = mode === 'edit' ? 'PUT' : 'POST';
  const result = await api(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  await loadRows();
  await openDetail(result.id_publicacion || id);
  setStatus(mode === 'edit' ? 'Publicacion actualizada.' : 'Publicacion creada.');
}

async function deletePublication(id) {
  if (!confirm(`Eliminar la publicacion ${id}? Esta accion no se puede deshacer.`)) return;
  await api(`/api/publicaciones/${id}`, { method: 'DELETE' });
  closeDetailPanel();
  await loadRows();
  setStatus('Publicacion eliminada.');
}

function detailField(label, value) {
  const display = value === null || value === undefined || value === '' ? '-' : value;
  return `
    <div class="detail-field">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(display)}</strong>
    </div>
  `;
}

function formatBoolean(value) {
  if (value === 1 || value === true) return 'Si';
  if (value === 0 || value === false) return 'No';
  return '';
}

function openImageViewer(index) {
  if (!currentImages.length) return;
  currentImageIndex = Math.max(0, Math.min(index, currentImages.length - 1));
  let viewer = document.querySelector('#imageViewer');
  if (!viewer) {
    viewer = document.createElement('div');
    viewer.id = 'imageViewer';
    viewer.className = 'image-viewer';
    viewer.innerHTML = `
      <div class="image-viewer-bar">
        <button class="secondary" id="prevImage" type="button">Anterior</button>
        <span id="imageCounter"></span>
        <button class="secondary" id="nextImage" type="button">Siguiente</button>
        <button class="secondary" id="toggleImageFit" type="button">Zoom</button>
        <button id="closeImageViewer" type="button">Cerrar</button>
      </div>
      <img id="largeImage" alt="">
    `;
    document.body.appendChild(viewer);
    viewer.querySelector('#closeImageViewer').addEventListener('click', closeImageViewer);
    viewer.querySelector('#prevImage').addEventListener('click', () => showImage(currentImageIndex - 1));
    viewer.querySelector('#nextImage').addEventListener('click', () => showImage(currentImageIndex + 1));
    viewer.querySelector('#toggleImageFit').addEventListener('click', () => {
      viewer.classList.toggle('zoomed');
      viewer.querySelector('#toggleImageFit').textContent = viewer.classList.contains('zoomed') ? 'Ajustar' : 'Zoom';
    });
    viewer.addEventListener('click', (event) => {
      if (event.target === viewer) closeImageViewer();
    });
  }
  viewer.classList.add('open');
  viewer.classList.remove('zoomed');
  viewer.querySelector('#toggleImageFit').textContent = 'Zoom';
  showImage(currentImageIndex);
}

function showImage(index) {
  if (!currentImages.length) return;
  currentImageIndex = (index + currentImages.length) % currentImages.length;
  const image = currentImages[currentImageIndex];
  document.querySelector('#largeImage').src = image.src;
  document.querySelector('#largeImage').alt = image.alt;
  document.querySelector('#imageCounter').textContent = `${currentImageIndex + 1} / ${currentImages.length}`;
}

function closeImageViewer() {
  document.querySelector('#imageViewer')?.classList.remove('open');
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

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, '&#096;');
}

function closeDetailPanel() {
  detail.classList.remove('open');
  document.body.classList.remove('detail-open');
}

refreshButton.addEventListener('click', () => loadRows().catch((error) => setStatus(error.message)));
fuenteInput.addEventListener('change', () => loadRows().catch((error) => setStatus(error.message)));
createButton.addEventListener('click', () => openPublicationForm('create'));
closeDetail.addEventListener('click', () => {
  closeDetailPanel();
});

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
    ? 'sin limite'
    : `${status.scanMode?.maxPages || 0} paginas / ${status.scanMode?.maxListingsPerSource || 0} publicaciones`;
  const speed = `paralelo ${status.scanMode?.scanConcurrency || 1} | ${status.scanMode?.downloadImages ? 'con imagenes' : 'sin imagenes'} | ${status.scanMode?.saveEvidence ? 'con evidencias' : 'sin evidencias'}`;
  const totals = (status.lastSummaries || [])
    .map((summary) => `${summary.source}: ${summary.totalGuardadas} guardadas, ${summary.totalOmitidas || 0} omitidas, ${summary.totalDescartadas} descartadas`)
    .join(' | ');
  botMeta.textContent = `Cada ${status.intervalMinutes} min | ${mode} | ${speed} | ultimo: ${last} | proximo: ${next}${totals ? ` | ${totals}` : ''}${status.lastError ? ` | error: ${status.lastError}` : ''}`;
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
