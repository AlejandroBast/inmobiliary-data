"use server"

import { readFile } from "node:fs/promises"
import path from "node:path"
import { db, pool } from "@/lib/db"
import { fuentesInmobiliarias, publicaciones } from "@/lib/db/schema"
import { and, desc, eq, sql } from "drizzle-orm"
import type { ResultSetHeader, RowDataPacket } from "mysql2"
import type { PoolConnection } from "mysql2/promise"
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
  duplicados?: string | null
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
  // true = disponible, false = roto, null = no se pudo verificar (p.ej. Facebook sin sesion)
  ok: boolean | null
  status: number | null
  error?: string
}

export type PublicacionLinkStatus = {
  id: number
  ok: boolean | null
  checkedAt: string
  links: PublicacionLinkCheck[]
}

export type CoincidenciaPublicacion = {
  id: number
  publicacionRelacionadaId: number
  puntaje: number
  estado: "pendiente" | "confirmada" | "descartada"
  imagenesCoincidentes: number
  distanciaMetros: number | null
  fuenteRelacionada: string | null
  precioRelacionado: string
}

export type ComparacionPublicacion = {
  id: number
  coincidenciaId: number | null
  fuenteNombre: string | null
  linkOrigen: string
  codigoExterno: string | null
  tipoInmueble: string | null
  ciudad: string | null
  barrio: string | null
  direccion: string | null
  ph: string | null
  precio: string
  m2: string | null
  m2Construido: string | null
  habitaciones: number | null
  banios: number | null
  parqueadero: number | null
  estrato: number | null
  administracion: string | null
  descripcion: string | null
  puntaje: number | null
  estado: "pendiente" | "confirmada" | null
  imagenesCoincidentes: number
}

interface CoincidenciaRow extends RowDataPacket {
  id: number
  publicacionId: number
  candidataId: number
  puntaje: string | number
  estado: "pendiente" | "confirmada" | "descartada"
  imagenesCoincidentes: number
  distanciaMetros: string | number | null
  precioPublicacion: string | number
  precioCandidata: string | number
  fuentePublicacion: string | null
  fuenteCandidata: string | null
}

interface CoincidenciaRevisionRow extends RowDataPacket {
  id: number
  publicacionId: number
  candidataId: number
  estado: "pendiente" | "confirmada" | "descartada"
}

interface GrupoDuplicadosRow extends RowDataPacket {
  inmuebleId: number
  estado: "automatico" | "pendiente" | "confirmado"
}

interface MiembroGrupoRow extends RowDataPacket {
  publicacionId: number
}

interface AristaGrupoRow extends RowDataPacket {
  publicacionId: number
  candidataId: number
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

  const duplicados = cleanFilter(filters.duplicados)
  if (duplicados === "con") {
    conditions.push(sql`EXISTS (
      SELECT 1 FROM coincidencias_publicaciones cp
      WHERE (cp.publicacion_id = ${publicaciones.id} OR cp.candidata_id = ${publicaciones.id})
        AND cp.estado <> 'descartada'
    )`)
  } else if (duplicados === "confirmadas" || duplicados === "pendientes") {
    const estado = duplicados === "confirmadas" ? "confirmada" : "pendiente"
    conditions.push(sql`EXISTS (
      SELECT 1 FROM coincidencias_publicaciones cp
      WHERE (cp.publicacion_id = ${publicaciones.id} OR cp.candidata_id = ${publicaciones.id})
        AND cp.estado = ${estado}
    )`)
  } else if (duplicados === "sin") {
    conditions.push(sql`NOT EXISTS (
      SELECT 1 FROM coincidencias_publicaciones cp
      WHERE (cp.publicacion_id = ${publicaciones.id} OR cp.candidata_id = ${publicaciones.id})
        AND cp.estado <> 'descartada'
    )`)
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

export async function getCoincidenciasPublicaciones(publicacionIds: number[]) {
  const ids = [...new Set(publicacionIds.filter((id) => Number.isInteger(id) && id > 0))]
  const grouped: Record<number, CoincidenciaPublicacion[]> = {}
  if (ids.length === 0) return grouped

  const placeholders = ids.map(() => "?").join(", ")
  const [rows] = await pool.query<CoincidenciaRow[]>(
    `SELECT
       cp.id,
       cp.publicacion_id AS publicacionId,
       cp.candidata_id AS candidataId,
       cp.puntaje,
       cp.estado,
       cp.imagenes_coincidentes AS imagenesCoincidentes,
       cp.distancia_metros AS distanciaMetros,
       publicacion.precio AS precioPublicacion,
       candidata.precio AS precioCandidata,
       fuente_publicacion.nombre AS fuentePublicacion,
       fuente_candidata.nombre AS fuenteCandidata
     FROM coincidencias_publicaciones cp
     JOIN publicaciones publicacion ON publicacion.id = cp.publicacion_id
     JOIN publicaciones candidata ON candidata.id = cp.candidata_id
     LEFT JOIN fuentes_inmobiliarias fuente_publicacion ON fuente_publicacion.id = publicacion.fuente_id
     LEFT JOIN fuentes_inmobiliarias fuente_candidata ON fuente_candidata.id = candidata.fuente_id
     WHERE cp.estado <> 'descartada'
       AND (cp.publicacion_id IN (${placeholders}) OR cp.candidata_id IN (${placeholders}))
     ORDER BY cp.estado = 'confirmada' DESC, cp.puntaje DESC`,
    [...ids, ...ids],
  )

  const visibleIds = new Set(ids)
  for (const row of rows) {
    const sides = [Number(row.publicacionId), Number(row.candidataId)]
    for (const currentId of sides) {
      if (!visibleIds.has(currentId)) continue
      const relatedId = currentId === Number(row.publicacionId)
        ? Number(row.candidataId)
        : Number(row.publicacionId)
      const currentIsPublication = currentId === Number(row.publicacionId)
      grouped[currentId] ??= []
      grouped[currentId].push({
        id: Number(row.id),
        publicacionRelacionadaId: relatedId,
        puntaje: Number(row.puntaje),
        estado: row.estado,
        imagenesCoincidentes: Number(row.imagenesCoincidentes ?? 0),
        distanciaMetros: row.distanciaMetros == null ? null : Number(row.distanciaMetros),
        fuenteRelacionada: currentIsPublication ? row.fuenteCandidata : row.fuentePublicacion,
        precioRelacionado: String(currentIsPublication ? row.precioCandidata : row.precioPublicacion),
      })
    }
  }

  return grouped
}

export async function getComparacionPublicaciones(publicacionId: number): Promise<ComparacionPublicacion[]> {
  if (!Number.isInteger(publicacionId) || publicacionId <= 0) return []

  const [matches] = await pool.query<RowDataPacket[]>(
    `SELECT id, publicacion_id, candidata_id, puntaje, estado, imagenes_coincidentes
     FROM coincidencias_publicaciones
     WHERE estado <> 'descartada'
       AND (publicacion_id = ? OR candidata_id = ?)
     ORDER BY estado = 'confirmada' DESC, puntaje DESC`,
    [publicacionId, publicacionId],
  )
  const ids = [...new Set([
    publicacionId,
    ...matches.flatMap((match) => [Number(match.publicacion_id), Number(match.candidata_id)]),
  ])]
  const placeholders = ids.map(() => "?").join(", ")
  const [rows] = await pool.query<RowDataPacket[]>(
    `SELECT
       p.id, p.link_origen, p.codigo_externo, p.tipo_inmueble, p.ciudad,
       p.barrio, p.direccion, p.ph, p.precio, p.m2, p.m2_construido,
       p.habitaciones, p.banios, p.parqueadero, p.estrato,
       p.administracion, p.descripcion, f.nombre AS fuente_nombre
     FROM publicaciones p
     LEFT JOIN fuentes_inmobiliarias f ON f.id = p.fuente_id
     WHERE p.id IN (${placeholders})`,
    ids,
  )

  const matchById = new Map<number, RowDataPacket>()
  for (const match of matches) {
    const relatedId = Number(match.publicacion_id) === publicacionId
      ? Number(match.candidata_id)
      : Number(match.publicacion_id)
    matchById.set(relatedId, match)
  }

  return rows
    .map((row) => {
      const id = Number(row.id)
      const match = matchById.get(id)
      return {
        id,
        coincidenciaId: match == null ? null : Number(match.id),
        fuenteNombre: row.fuente_nombre == null ? null : String(row.fuente_nombre),
        linkOrigen: String(row.link_origen),
        codigoExterno: row.codigo_externo == null ? null : String(row.codigo_externo),
        tipoInmueble: row.tipo_inmueble == null ? null : String(row.tipo_inmueble),
        ciudad: row.ciudad == null ? null : String(row.ciudad),
        barrio: row.barrio == null ? null : String(row.barrio),
        direccion: row.direccion == null ? null : String(row.direccion),
        ph: row.ph == null ? null : String(row.ph),
        precio: String(row.precio),
        m2: row.m2 == null ? null : String(row.m2),
        m2Construido: row.m2_construido == null ? null : String(row.m2_construido),
        habitaciones: row.habitaciones == null ? null : Number(row.habitaciones),
        banios: row.banios == null ? null : Number(row.banios),
        parqueadero: row.parqueadero == null ? null : Number(row.parqueadero),
        estrato: row.estrato == null ? null : Number(row.estrato),
        administracion: row.administracion == null ? null : String(row.administracion),
        descripcion: row.descripcion == null ? null : String(row.descripcion),
        puntaje: match == null ? null : Number(match.puntaje),
        estado: match == null ? null : match.estado as "pendiente" | "confirmada",
        imagenesCoincidentes: match == null ? 0 : Number(match.imagenes_coincidentes ?? 0),
      }
    })
    .sort((first, second) => first.id === publicacionId ? -1 : second.id === publicacionId ? 1 : (second.puntaje ?? 0) - (first.puntaje ?? 0))
}

function connectedDuplicateComponents(publicationIds: number[], edges: AristaGrupoRow[]) {
  const adjacency = new Map<number, Set<number>>(
    publicationIds.map((publicationId) => [publicationId, new Set<number>()]),
  )

  for (const edge of edges) {
    const firstId = Number(edge.publicacionId)
    const secondId = Number(edge.candidataId)
    if (!adjacency.has(firstId) || !adjacency.has(secondId)) continue
    adjacency.get(firstId)?.add(secondId)
    adjacency.get(secondId)?.add(firstId)
  }

  const visited = new Set<number>()
  const components: number[][] = []
  for (const publicationId of publicationIds) {
    if (visited.has(publicationId)) continue
    const component: number[] = []
    const pending = [publicationId]
    visited.add(publicationId)

    while (pending.length > 0) {
      const currentId = pending.pop()
      if (currentId == null) continue
      component.push(currentId)
      for (const neighborId of adjacency.get(currentId) ?? []) {
        if (visited.has(neighborId)) continue
        visited.add(neighborId)
        pending.push(neighborId)
      }
    }
    components.push(component)
  }

  return components
}

async function rebuildDuplicateGroup(
  connection: PoolConnection,
  groupId: number,
  groupState: GrupoDuplicadosRow["estado"],
) {
  const [memberRows] = await connection.query<MiembroGrupoRow[]>(
    `SELECT publicacion_id AS publicacionId
     FROM publicaciones_inmueble
     WHERE inmueble_id = ?
     FOR UPDATE`,
    [groupId],
  )
  const memberIds = memberRows.map((row) => Number(row.publicacionId))

  if (memberIds.length < 2) {
    await connection.query("DELETE FROM inmuebles_detectados WHERE id = ?", [groupId])
    return
  }

  const placeholders = memberIds.map(() => "?").join(", ")
  const [edges] = await connection.query<AristaGrupoRow[]>(
    `SELECT publicacion_id AS publicacionId, candidata_id AS candidataId
     FROM coincidencias_publicaciones
     WHERE estado = 'confirmada'
       AND publicacion_id IN (${placeholders})
       AND candidata_id IN (${placeholders})`,
    [...memberIds, ...memberIds],
  )
  const groupedComponents = connectedDuplicateComponents(memberIds, edges)
    .filter((component) => component.length >= 2)
    .sort((first, second) => second.length - first.length)

  if (groupedComponents.length === 0) {
    await connection.query("DELETE FROM inmuebles_detectados WHERE id = ?", [groupId])
    return
  }

  const stillGrouped = new Set(groupedComponents.flat())
  const singlePublications = memberIds.filter((publicationId) => !stillGrouped.has(publicationId))
  if (singlePublications.length > 0) {
    const singlePlaceholders = singlePublications.map(() => "?").join(", ")
    await connection.query(
      `DELETE FROM publicaciones_inmueble
       WHERE inmueble_id = ? AND publicacion_id IN (${singlePlaceholders})`,
      [groupId, ...singlePublications],
    )
  }

  for (const component of groupedComponents.slice(1)) {
    const [createdGroup] = await connection.query<ResultSetHeader>(
      "INSERT INTO inmuebles_detectados (estado) VALUES (?)",
      [groupState],
    )
    const componentPlaceholders = component.map(() => "?").join(", ")
    await connection.query(
      `UPDATE publicaciones_inmueble
       SET inmueble_id = ?
       WHERE inmueble_id = ? AND publicacion_id IN (${componentPlaceholders})`,
      [createdGroup.insertId, groupId, ...component],
    )
  }
}

export async function descartarCoincidenciaPublicaciones(coincidenciaId: number) {
  if (!Number.isInteger(coincidenciaId) || coincidenciaId <= 0) {
    return { success: false as const, error: "La coincidencia seleccionada no es valida." }
  }

  const connection = await pool.getConnection()
  try {
    await connection.beginTransaction()
    const [matches] = await connection.query<CoincidenciaRevisionRow[]>(
      `SELECT id, publicacion_id AS publicacionId, candidata_id AS candidataId, estado
       FROM coincidencias_publicaciones
       WHERE id = ?
       FOR UPDATE`,
      [coincidenciaId],
    )
    const match = matches[0]
    if (!match) throw new Error("La coincidencia ya no existe.")

    await connection.query(
      `UPDATE coincidencias_publicaciones
       SET estado = 'descartada', fecha_revision = CURRENT_TIMESTAMP
       WHERE id = ?`,
      [coincidenciaId],
    )

    if (match.estado === "confirmada") {
      const [groupRows] = await connection.query<GrupoDuplicadosRow[]>(
        `SELECT pi.inmueble_id AS inmuebleId, inmueble.estado
         FROM publicaciones_inmueble pi
         JOIN inmuebles_detectados inmueble ON inmueble.id = pi.inmueble_id
         WHERE pi.publicacion_id IN (?, ?)
         FOR UPDATE`,
        [Number(match.publicacionId), Number(match.candidataId)],
      )
      const affectedGroups = new Map<number, GrupoDuplicadosRow["estado"]>()
      for (const row of groupRows) {
        affectedGroups.set(Number(row.inmuebleId), row.estado)
      }
      for (const [groupId, groupState] of affectedGroups) {
        await rebuildDuplicateGroup(connection, groupId, groupState)
      }
    }

    await connection.commit()
  } catch (error) {
    await connection.rollback()
    return { success: false as const, error: parseError(error) }
  } finally {
    connection.release()
  }

  revalidatePath("/")
  return { success: true as const }
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

const FACEBOOK_HOSTNAME_RE = /(^|\.)facebook\.com$/i
const FACEBOOK_COOKIES_TTL_MS = 60_000

type FacebookCookie = { name: string; value: string; domain?: string }

let facebookCookieCache: { header: string | null; loadedAt: number } | null = null

function facebookUnknownCheck(label: string, url: string, status: number | null, error: string): PublicacionLinkCheck {
  return { label, url, ok: null, status, error }
}

function facebookCookiesPath() {
  // El scraper (Python) exporta las cookies en .facebook_profile/session_cookies.json
  // desde la raiz del repo. El front corre desde /front, por eso subimos un nivel.
  return (
    process.env.FACEBOOK_SESSION_COOKIES_PATH ||
    path.join(process.cwd(), "..", ".facebook_profile", "session_cookies.json")
  )
}

async function getFacebookCookieHeader(): Promise<string | null> {
  if (facebookCookieCache && Date.now() - facebookCookieCache.loadedAt < FACEBOOK_COOKIES_TTL_MS) {
    return facebookCookieCache.header
  }
  try {
    const raw = await readFile(facebookCookiesPath(), "utf-8")
    const parsed = JSON.parse(raw) as { cookies?: FacebookCookie[] }
    const cookies = parsed.cookies ?? []
    const header = cookies.length ? cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ") : null
    facebookCookieCache = { header, loadedAt: Date.now() }
    return header
  } catch {
    facebookCookieCache = { header: null, loadedAt: Date.now() }
    return null
  }
}

async function validateLink(
  label: string,
  url: string,
  facebookCookieHeader: string | null,
): Promise<PublicacionLinkCheck> {
  if (!/^https?:\/\//i.test(url)) {
    return { label, url, ok: false, status: null, error: "URL invalida" }
  }

  let parsedUrl: URL
  try {
    parsedUrl = new URL(url)
  } catch {
    return { label, url, ok: false, status: null, error: "URL invalida" }
  }

  const isFacebook = FACEBOOK_HOSTNAME_RE.test(parsedUrl.hostname)

  if (isFacebook && !facebookCookieHeader) {
    return facebookUnknownCheck(
      label,
      url,
      null,
      "Sin sesion de Facebook exportada. Ejecuta el scraper para refrescarla.",
    )
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
        ...(isFacebook && facebookCookieHeader ? { Cookie: facebookCookieHeader } : {}),
      },
    })

    const statusOk = response.status >= 200 && response.status < 400

    if (isFacebook) {
      const finalUrl = response.url.toLowerCase()
      if (finalUrl.includes("/login") || finalUrl.includes("/checkpoint")) {
        return facebookUnknownCheck(
          label,
          url,
          response.status,
          "La sesion de Facebook expiro. Ejecuta el scraper para refrescarla.",
        )
      }

      if (!statusOk) {
        return facebookUnknownCheck(
          label,
          url,
          response.status,
          `Facebook no permitio verificar este link (HTTP ${response.status}). Refresca la sesion con el scraper.`,
        )
      }

      const body = (await response.text()).toLowerCase()
      if (
        body.includes("login to facebook") ||
        body.includes("log in to facebook") ||
        body.includes("iniciar sesion") ||
        body.includes("inicia sesion") ||
        body.includes("checkpoint")
      ) {
        return facebookUnknownCheck(
          label,
          url,
          response.status,
          "Facebook mostro login/checkpoint. Ejecuta el scraper para refrescar la sesion.",
        )
      }
    }

    return {
      label,
      url,
      ok: statusOk,
      status: response.status,
      error: statusOk ? undefined : `HTTP ${response.status}`,
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "No se pudo validar"
    if (isFacebook) {
      return facebookUnknownCheck(
        label,
        url,
        null,
        message.includes("aborted")
          ? "Tiempo de espera agotado validando Facebook; no se marca como roto."
          : `Facebook no permitio completar la verificacion: ${message}`,
      )
    }

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
  const facebookCookieHeader = await getFacebookCookieHeader()

  return Promise.all(
    items.map(async (item) => {
      const links = normalizeStoredLinks(item)
      const checks = await Promise.all(
        links.map((link) => validateLink(link.label, link.url, facebookCookieHeader)),
      )

      const hasBroken = checks.some((check) => check.ok === false)
      const hasUnknown = checks.some((check) => check.ok === null)

      return {
        id: item.id,
        ok: checks.length === 0 || hasBroken ? false : hasUnknown ? null : true,
        checkedAt: new Date().toISOString(),
        links: checks,
      }
    }),
  )
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
