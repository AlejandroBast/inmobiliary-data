"use server"

import { db } from "@/lib/db"
import { fuentesInmobiliarias, publicaciones } from "@/lib/db/schema"
import { desc, eq } from "drizzle-orm"
import { revalidatePath } from "next/cache"

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

// READ
export async function getPublicaciones() {
  return db
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
    .orderBy(desc(publicaciones.fechaCaptura))
}

export async function getFuentes() {
  return db.select().from(fuentesInmobiliarias).orderBy(fuentesInmobiliarias.nombre)
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
