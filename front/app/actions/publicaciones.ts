"use server"

import { db } from "@/lib/db"
import { fuentesInmobiliarias, publicaciones } from "@/lib/db/schema"
import { and, desc, eq, sql } from "drizzle-orm"
import { revalidatePath } from "next/cache"

export type PublicacionFilters = {
  id?: string | null
  tipoInmueble?: string | null
  fuenteId?: string | null
  fecha?: string | null
  habitaciones?: string | null
  banios?: string | null
  barrio?: string | null
  ubicacion?: string | null
  precioMin?: string | null
  precioMax?: string | null
  m2Min?: string | null
  m2Max?: string | null
  phTipo?: string | null
  parqueadero?: string | null
  page?: string | null
  pageSize?: string | null
}

const DEFAULT_PAGE_SIZE = 50
const MAX_PAGE_SIZE = 100

export type PublicacionInput = {
  fuenteId: number
  codigoExterno?: string | null
  linkOrigen: string
  linksAdicionales?: string[] | null
  coordenadas?: string | null
  latitud?: string | null
  longitud?: string | null
  direccion?: string | null
  ciudad?: string | null
  barrio?: string | null
  tipoInmueble?: string | null
  ph?: string | null
  estrato?: number | null
  descripcion?: string | null
  precio: number
  m2?: string | null
  m2Construido?: string | null
  antiguedad?: string | null
  pisos?: number | null
  habitaciones?: number | null
  banios?: number | null
  parqueadero?: number | null
  administracion?: string | null
  notas?: string | null
}

export type PublicacionLinkValidationInput = {
  id: number
  linkOrigen?: string | null
  linksAdicionales?: unknown
}

export type PublicacionLinkCheck = {
  label: string
  url: string
  ok: boolean
  status: number | null
  error?: string
}

export type PublicacionLinkStatus = {
  id: number
  ok: boolean
  checkedAt: string
  links: PublicacionLinkCheck[]
}

function cleanFilter(value?: string | null) {
  const cleaned = value?.trim()
  return cleaned ? cleaned : null
}

function parseNumericFilter(value?: string | null) {
  const cleaned = cleanFilter(value)
  if (!cleaned) return null

  if (cleaned.endsWith("+")) {
    const parsed = Number.parseInt(cleaned.slice(0, -1), 10)
    return Number.isNaN(parsed) ? null : { type: "gte" as const, value: parsed }
  }

  const parsed = Number.parseInt(cleaned, 10)
  return Number.isNaN(parsed) ? null : { type: "eq" as const, value: parsed }
}

function normalizeBarrio(value?: string | null) {
  const normalized = value
    ?.normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[.,;:_/\\-]+/g, " ")
    .replace(/^(barrio|b|br|bo)\s+/, "")
    .replace(/\s+/g, " ")
    .trim()

  return normalized || null
}

function barrioSql() {
  const withoutAccents = sql<string>`LOWER(
    REPLACE(
      REPLACE(
        REPLACE(
          REPLACE(
            REPLACE(
              REPLACE(
                REPLACE(
                  REPLACE(
                    REPLACE(
                      REPLACE(
                        REPLACE(
                          REPLACE(TRIM(${publicaciones.barrio}), 'Á', 'a'),
                          'É', 'e'
                        ),
                        'Í', 'i'
                      ),
                      'Ó', 'o'
                    ),
                    'Ú', 'u'
                  ),
                  'Ü', 'u'
                ),
                'Ñ', 'n'
              ),
              'á', 'a'
            ),
            'é', 'e'
          ),
          'í', 'i'
        ),
        'ó', 'o'
      ),
      'ú', 'u'
    )
  )`

  const withoutPunctuation = sql<string>`REGEXP_REPLACE(${withoutAccents}, ${"[.,;:_/\\\\-]+"}, ${" "})`
  const withoutPrefix = sql<string>`REGEXP_REPLACE(${withoutPunctuation}, ${"^(barrio|b|br|bo)\\s+"}, ${""})`

  return sql<string>`TRIM(REGEXP_REPLACE(${withoutPrefix}, ${"\\s+"}, ${" "}))`
}

function parseMoneyFilter(value?: string | null) {
  const cleaned = cleanFilter(value)?.replace(/\D/g, "")
  if (!cleaned) return null

  const parsed = Number.parseInt(cleaned, 10)
  if (Number.isNaN(parsed)) return null

  return parsed > 0 && parsed < 100000 ? parsed * 1_000_000 : parsed
}

function parseAreaFilter(value?: string | null) {
  const cleaned = cleanFilter(value)?.replace(",", ".").replace(/[^\d.]/g, "")
  if (!cleaned) return null

  const parsed = Number.parseFloat(cleaned)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function m2Sql() {
  return sql<number>`CAST(NULLIF(REGEXP_REPLACE(REPLACE(${publicaciones.m2}, ',', '.'), ${"[^0-9.]"}, ${""}), '') AS DECIMAL(10,2))`
}

function isValidDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(`${value}T00:00:00`).getTime())
}

// READ
function buildPublicacionConditions(filters: PublicacionFilters = {}) {
  const conditions = [] as Array<ReturnType<typeof sql>>

  const id = cleanFilter(filters.id)
  if (id) {
    const parsedId = Number.parseInt(id, 10)
    if (!Number.isNaN(parsedId)) {
      conditions.push(eq(publicaciones.id, parsedId))
    }
  }

  const tipoInmueble = cleanFilter(filters.tipoInmueble)
  if (tipoInmueble) {
    conditions.push(sql`${publicaciones.tipoInmueble} LIKE ${`%${tipoInmueble}%`}`)
  }

  const fuenteId = cleanFilter(filters.fuenteId)
  if (fuenteId) {
    const parsedFuenteId = Number.parseInt(fuenteId, 10)
    if (!Number.isNaN(parsedFuenteId)) {
      conditions.push(eq(publicaciones.fuenteId, parsedFuenteId))
    }
  }

  const fecha = cleanFilter(filters.fecha)
  if (fecha && isValidDate(fecha)) {
    conditions.push(sql`DATE(${publicaciones.fechaCaptura}) = ${fecha}`)
  }

  const habitaciones = parseNumericFilter(filters.habitaciones)
  if (habitaciones) {
    conditions.push(
      habitaciones.type === "gte"
        ? sql`${publicaciones.habitaciones} >= ${habitaciones.value}`
        : eq(publicaciones.habitaciones, habitaciones.value),
    )
  }

  const banios = parseNumericFilter(filters.banios)
  if (banios) {
    conditions.push(
      banios.type === "gte"
        ? sql`${publicaciones.banios} >= ${banios.value}`
        : eq(publicaciones.banios, banios.value),
    )
  }

  const parqueadero = parseNumericFilter(filters.parqueadero)
  if (parqueadero) {
    conditions.push(
      parqueadero.type === "gte"
        ? sql`${publicaciones.parqueadero} >= ${parqueadero.value}`
        : eq(publicaciones.parqueadero, parqueadero.value),
    )
  }

  const precioMin = parseMoneyFilter(filters.precioMin)
  if (precioMin) {
    conditions.push(sql`${publicaciones.precio} >= ${precioMin}`)
  }

  const precioMax = parseMoneyFilter(filters.precioMax)
  if (precioMax) {
    conditions.push(sql`${publicaciones.precio} <= ${precioMax}`)
  }

  const m2Min = parseAreaFilter(filters.m2Min)
  if (m2Min) {
    conditions.push(sql`${m2Sql()} >= ${m2Min}`)
  }

  const m2Max = parseAreaFilter(filters.m2Max)
  if (m2Max) {
    conditions.push(sql`${m2Sql()} <= ${m2Max}`)
  }

  const phTipo = cleanFilter(filters.phTipo)
  if (phTipo === "ph") {
    conditions.push(sql`${publicaciones.ph} IS NOT NULL AND TRIM(${publicaciones.ph}) <> ''`)
  } else if (phTipo === "normal") {
    conditions.push(sql`(${publicaciones.ph} IS NULL OR TRIM(${publicaciones.ph}) = '')`)
  }

  const barrio = cleanFilter(filters.barrio) ?? cleanFilter(filters.ubicacion)
  if (barrio === "__sin_barrio") {
    conditions.push(sql`(${publicaciones.barrio} IS NULL OR TRIM(${publicaciones.barrio}) = '')`)
  } else {
    const barrioNormalizado = normalizeBarrio(barrio)
    if (barrioNormalizado) {
      conditions.push(sql`${barrioSql()} = ${barrioNormalizado}`)
    }
  }

  return conditions
}

function parsePagination(filters: PublicacionFilters = {}) {
  const parsedPage = Number.parseInt(cleanFilter(filters.page) ?? "1", 10)
  const parsedPageSize = Number.parseInt(cleanFilter(filters.pageSize) ?? String(DEFAULT_PAGE_SIZE), 10)
  const page = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1
  const pageSize = Math.min(
    MAX_PAGE_SIZE,
    Math.max(1, Number.isFinite(parsedPageSize) && parsedPageSize > 0 ? parsedPageSize : DEFAULT_PAGE_SIZE),
  )
  return { page, pageSize, offset: (page - 1) * pageSize }
}

export async function getPublicaciones(filters: PublicacionFilters = {}) {
  const conditions = buildPublicacionConditions(filters)
  const { page, pageSize, offset } = parsePagination(filters)

  const rows = await db
    .select({
      id: publicaciones.id,
      fuenteId: publicaciones.fuenteId,
      fuenteNombre: fuentesInmobiliarias.nombre,
      codigoExterno: publicaciones.codigoExterno,
      linkOrigen: publicaciones.linkOrigen,
      linksAdicionales: publicaciones.linksAdicionales,
      fechaCaptura: publicaciones.fechaCaptura,
      coordenadas: publicaciones.coordenadas,
      latitud: publicaciones.latitud,
      longitud: publicaciones.longitud,
      direccion: publicaciones.direccion,
      ciudad: publicaciones.ciudad,
      barrio: publicaciones.barrio,
      tipoInmueble: publicaciones.tipoInmueble,
      ph: publicaciones.ph,
      estrato: publicaciones.estrato,
      descripcion: publicaciones.descripcion,
      precio: publicaciones.precio,
      m2: publicaciones.m2,
      precioM2: publicaciones.precioM2,
      m2Construido: publicaciones.m2Construido,
      precioM2Construido: publicaciones.precioM2Construido,
      antiguedad: publicaciones.antiguedad,
      pisos: publicaciones.pisos,
      habitaciones: publicaciones.habitaciones,
      banios: publicaciones.banios,
      parqueadero: publicaciones.parqueadero,
      administracion: publicaciones.administracion,
      notas: publicaciones.notas,
    })
    .from(publicaciones)
    .leftJoin(fuentesInmobiliarias, eq(publicaciones.fuenteId, fuentesInmobiliarias.id))
    .where(conditions.length > 0 ? and(...conditions) : undefined)
    .orderBy(desc(publicaciones.fechaCaptura))
    .limit(pageSize)
    .offset(offset)

  const total = await getPublicacionesTotal(filters)

  return {
    data: rows,
    total,
    page,
    pageSize,
    totalPages: Math.max(1, Math.ceil(total / pageSize)),
  }
}

function normalizeStoredLinks(input: PublicacionLinkValidationInput) {
  const links: Array<{ label: string; url: string }> = []
  const origen = cleanFilter(input.linkOrigen)

  if (origen) {
    links.push({ label: "Origen", url: origen })
  }

  const adicionales = input.linksAdicionales
  const rawLinks = Array.isArray(adicionales)
    ? adicionales
    : typeof adicionales === "string"
      ? adicionales.split(/\r?\n/)
      : []

  rawLinks.forEach((item, index) => {
    const url = typeof item === "string" ? cleanFilter(item) : null
    if (url) {
      links.push({ label: `Adicional ${index + 1}`, url })
    }
  })

  return links
}

async function validateLink(label: string, url: string): Promise<PublicacionLinkCheck> {
  if (!/^https?:\/\//i.test(url)) {
    return { label, url, ok: false, status: null, error: "URL invalida" }
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8000)

  try {
    const response = await fetch(url, {
      method: "GET",
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    })

    return {
      label,
      url,
      ok: response.status >= 200 && response.status < 400,
      status: response.status,
      error: response.status >= 200 && response.status < 400 ? undefined : `HTTP ${response.status}`,
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "No se pudo validar"
    return {
      label,
      url,
      ok: false,
      status: null,
      error: message.includes("aborted") ? "Tiempo de espera agotado" : message,
    }
  } finally {
    clearTimeout(timeout)
  }
}

export async function validatePublicacionLinks(
  items: PublicacionLinkValidationInput[],
): Promise<PublicacionLinkStatus[]> {
  return Promise.all(
    items.map(async (item) => {
      const links = normalizeStoredLinks(item)
      const checks = await Promise.all(links.map((link) => validateLink(link.label, link.url)))

      return {
        id: item.id,
        ok: checks.length > 0 && checks.every((check) => check.ok),
        checkedAt: new Date().toISOString(),
        links: checks,
      }
    }),
  )
}

export async function getPublicacionesTotal(filters: PublicacionFilters = {}) {
  const conditions = buildPublicacionConditions(filters)
  const [row] = await db
    .select({
      total: sql<number>`COUNT(*)`,
    })
    .from(publicaciones)
    .where(conditions.length > 0 ? and(...conditions) : undefined)

  return Number(row?.total ?? 0)
}

export async function getFuentes() {
  return db.select().from(fuentesInmobiliarias).orderBy(fuentesInmobiliarias.nombre)
}

export async function getBarrios() {
  const rows = await db
    .select({
      barrio: publicaciones.barrio,
    })
    .from(publicaciones)
    .where(sql`${publicaciones.barrio} IS NOT NULL AND TRIM(${publicaciones.barrio}) <> ''`)
    .groupBy(publicaciones.barrio)
    .orderBy(publicaciones.barrio)

  const options = new Map<string, string>()

  for (const row of rows) {
    const normalized = normalizeBarrio(row.barrio)
    const label = row.barrio?.replace(/\s+/g, " ").trim()
    if (normalized && label && !options.has(normalized)) {
      options.set(normalized, label)
    }
  }

  const [sinBarrio] = await db
    .select({
      total: sql<number>`COUNT(*)`,
    })
    .from(publicaciones)
    .where(sql`${publicaciones.barrio} IS NULL OR TRIM(${publicaciones.barrio}) = ''`)

  return {
    barrios: Array.from(options, ([value, label]) => ({ value, label })).sort((a, b) =>
      a.label.localeCompare(b.label, "es"),
    ),
    hasSinBarrio: Number(sinBarrio?.total ?? 0) > 0,
  }
}

export async function createFuente(input: { nombre: string; tipoFuente?: string | null; urlBase?: string | null }) {
  try {
    const inserted = await db
      .insert(fuentesInmobiliarias)
      .values({
        nombre: input.nombre,
        tipoFuente: input.tipoFuente || null,
        urlBase: input.urlBase || null,
      })
      .$returningId()

    const fuenteId = inserted[0]?.id

    if (!fuenteId) {
      return { success: false as const, error: "No se pudo crear la fuente." }
    }

    const [row] = await db
      .select()
      .from(fuentesInmobiliarias)
      .where(eq(fuentesInmobiliarias.id, fuenteId))
      .limit(1)

    revalidatePath("/")
    return { success: true as const, fuente: row ?? null }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    if (message.includes("Duplicate entry") || message.includes("1062")) {
      return { success: false as const, error: "Ya existe una fuente con ese nombre." }
    }
    return { success: false as const, error: message }
  }
}

function toValues(input: PublicacionInput) {
  return {
    fuenteId: input.fuenteId,
    codigoExterno: input.codigoExterno || null,
    linkOrigen: input.linkOrigen,
    linksAdicionales: input.linksAdicionales && input.linksAdicionales.length > 0 ? input.linksAdicionales : null,
    coordenadas: input.coordenadas || null,
    latitud: input.latitud || null,
    longitud: input.longitud || null,
    direccion: input.direccion || null,
    ciudad: input.ciudad || null,
    barrio: input.barrio || null,
    tipoInmueble: input.tipoInmueble || null,
    ph: input.ph || null,
    estrato: input.estrato ?? null,
    descripcion: input.descripcion || null,
    precio: String(input.precio),
    m2: input.m2 || null,
    m2Construido: input.m2Construido || null,
    antiguedad: input.antiguedad || null,
    pisos: input.pisos ?? null,
    habitaciones: input.habitaciones ?? null,
    banios: input.banios ?? null,
    parqueadero: input.parqueadero ?? null,
    administracion: input.administracion || null,
    notas: input.notas || null,
  }
}

// CREATE
export async function createPublicacion(input: PublicacionInput) {
  try {
    await db.insert(publicaciones).values(toValues(input))
    revalidatePath("/")
    return { success: true as const }
  } catch (error) {
    return { success: false as const, error: parseError(error) }
  }
}

// UPDATE
export async function updatePublicacion(id: number, input: PublicacionInput) {
  try {
    await db.update(publicaciones).set(toValues(input)).where(eq(publicaciones.id, id))
    revalidatePath("/")
    return { success: true as const }
  } catch (error) {
    return { success: false as const, error: parseError(error) }
  }
}

// DELETE
export async function deletePublicacion(id: number) {
  try {
    await db.delete(publicaciones).where(eq(publicaciones.id, id))
    revalidatePath("/")
    return { success: true as const }
  } catch (error) {
    return { success: false as const, error: parseError(error) }
  }
}

export async function updateNotaPublicacion(id: number, nota: string | null) {
  try {
    await db
      .update(publicaciones)
      .set({ notas: nota?.trim() ? nota.trim() : null })
      .where(eq(publicaciones.id, id))
    revalidatePath("/")
    return { success: true as const }
  } catch (error) {
    return { success: false as const, error: parseError(error) }
  }
}

function parseError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  if (message.includes("Duplicate entry") || message.includes("1062")) {
    if (message.includes("link_origen")) {
      return "Ya existe una publicación con ese link de origen."
    }
    if (message.includes("nombre")) {
      return "Ya existe una fuente con ese nombre."
    }
    return "Ya existe una publicación con ese link de origen."
  }
  if (message.includes("precio") && (message.includes("check") || message.includes("chk_precio"))) {
    return "El precio debe ser mayor a 0."
  }
  if (message.includes("foreign key") || message.includes("1452") || message.includes("fuente_id")) {
    return "La fuente seleccionada no es válida."
  }
  return message
}
