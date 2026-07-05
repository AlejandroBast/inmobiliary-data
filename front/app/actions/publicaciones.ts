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
  parqueadero?: string | null
}

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
  comuna?: string | null
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

function isValidDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(`${value}T00:00:00`).getTime())
}

// READ
export async function getPublicaciones(filters: PublicacionFilters = {}) {
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

  const barrio = cleanFilter(filters.barrio) ?? cleanFilter(filters.ubicacion)
  if (barrio === "__sin_barrio") {
    conditions.push(sql`(${publicaciones.barrio} IS NULL OR TRIM(${publicaciones.barrio}) = '')`)
  } else {
    const barrioNormalizado = normalizeBarrio(barrio)
    if (barrioNormalizado) {
      conditions.push(sql`${barrioSql()} = ${barrioNormalizado}`)
    }
  }

  const query = db
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
      comuna: publicaciones.comuna,
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

  return query
}

export async function getPublicacionesTotal() {
  const [row] = await db
    .select({
      total: sql<number>`COUNT(*)`,
    })
    .from(publicaciones)

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
    comuna: input.comuna || null,
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
