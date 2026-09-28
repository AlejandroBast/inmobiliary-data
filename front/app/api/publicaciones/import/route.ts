import { spawn } from "node:child_process"
import path from "node:path"
import { NextResponse } from "next/server"
import { eq } from "drizzle-orm"
import { db } from "@/lib/db"
import { fuentesInmobiliarias } from "@/lib/db/schema"
import { SCRAPER_SOURCES, type ScraperSourceId } from "@/lib/scrapers"

export const runtime = "nodejs"

const SOURCE_IDS = Object.keys(SCRAPER_SOURCES) as ScraperSourceId[]
const SCRAPER_TIMEOUT_MS = 120_000

type DraftData = Record<string, unknown>

type DraftPayload = {
  sourceId: ScraperSourceId
  data: DraftData
  imageUrls: string[]
}

function splitCommand(value: string) {
  const parts = value.match(/"[^"]+"|'[^']+'|\S+/g)?.map((part) => part.replace(/^["']|["']$/g, "")) ?? []
  return { command: parts[0] ?? value, args: parts.slice(1) }
}

function pythonCommand() {
  const configured = process.env.SCRAPER_PYTHON?.trim()
  if (configured) return splitCommand(configured)
  return process.platform === "win32" ? { command: "py", args: ["-3"] } : { command: "python3", args: [] }
}

function sourceForUrl(rawUrl: string) {
  let target: URL
  try {
    target = new URL(rawUrl)
  } catch {
    return null
  }

  if (target.protocol !== "http:" && target.protocol !== "https:") return null
  const hostname = target.hostname.toLowerCase().replace(/\.$/, "")
  if (!target.pathname || target.pathname === "/") return null

  return SOURCE_IDS.find((sourceId) => {
    const matchesHost = SCRAPER_SOURCES[sourceId].hostnames.some(
      (domain) => hostname === domain || hostname.endsWith(`.${domain}`),
    )
    if (!matchesHost) return false
    return sourceId !== "facebook" || target.pathname.toLowerCase().startsWith("/marketplace/")
  }) ?? null
}

function runDraftScraper(sourceId: ScraperSourceId, url: string): Promise<DraftPayload> {
  const projectDir = path.resolve(process.cwd(), "..")
  const scriptPath = path.join(projectDir, "scripts", "scrape_publication_draft.py")
  const python = pythonCommand()

  return new Promise((resolve, reject) => {
    const child = spawn(python.command, [...python.args, scriptPath, "--source", sourceId, "--url", url], {
      cwd: projectDir,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: [path.join(projectDir, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      },
      windowsHide: true,
    })
    let stdout = ""
    let stderr = ""
    const timeout = setTimeout(() => {
      child.kill()
      reject(new Error("El scraper tardo demasiado en responder."))
    }, SCRAPER_TIMEOUT_MS)

    child.stdout.on("data", (chunk) => { stdout += chunk.toString() })
    child.stderr.on("data", (chunk) => { stderr += chunk.toString() })
    child.on("error", (error) => {
      clearTimeout(timeout)
      reject(error)
    })
    child.on("close", (code) => {
      clearTimeout(timeout)
      if (code !== 0) {
        reject(new Error(stderr.trim() || "El scraper no pudo leer la publicación."))
        return
      }

      const lines = stdout.trim().split(/\r?\n/).filter(Boolean)
      try {
        resolve(JSON.parse(lines.at(-1) ?? "") as DraftPayload)
      } catch {
        reject(new Error("El scraper no devolvió un borrador válido."))
      }
    })
  })
}

function mapDraftData(data: DraftData, fuenteId: number | null, link: string) {
  return {
    fuenteId,
    codigoExterno: data.codigo_externo ?? null,
    linkOrigen: data.link_origen ?? link,
    linksAdicionales: null,
    coordenadas: data.coordenadas ?? null,
    latitud: data.latitud ?? null,
    longitud: data.longitud ?? null,
    direccion: data.direccion ?? null,
    ciudad: data.ciudad ?? null,
    barrio: data.barrio ?? null,
    tipoInmueble: data.tipo_inmueble ?? null,
    ph: data.ph ?? null,
    estrato: data.estrato ?? null,
    descripcion: data.descripcion ?? null,
    precio: data.precio ?? null,
    m2: data.m2 ?? null,
    m2Construido: data.m2_construido ?? null,
    antiguedad: data.antiguedad ?? null,
    pisos: data.pisos ?? null,
    habitaciones: data.habitaciones ?? null,
    banios: data.banios ?? null,
    parqueadero: data.parqueadero ?? null,
    administracion: data.administracion ?? null,
    notas: data.notas ?? null,
  }
}

export async function POST(request: Request) {
  let body: { url?: string }
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: "Solicitud invalida." }, { status: 400 })
  }

  const url = body.url?.trim() ?? ""
  const sourceId = sourceForUrl(url)
  if (!sourceId) {
    return NextResponse.json(
      { error: "La URL no es compatible. Usa un enlace de Amorel, Ciencuadras, Finca Raiz, Metrocuadrado o Facebook Marketplace." },
      { status: 400 },
    )
  }

  try {
    const sourceName = SCRAPER_SOURCES[sourceId].name
    const [fuente] = await db
      .select({ id: fuentesInmobiliarias.id })
      .from(fuentesInmobiliarias)
      .where(eq(fuentesInmobiliarias.nombre, sourceName))
      .limit(1)
    if (!fuente) {
      return NextResponse.json({ error: `La fuente ${sourceName} no está configurada en la base de datos.` }, { status: 500 })
    }

    const draft = await runDraftScraper(sourceId, url)
    return NextResponse.json({
      sourceId,
      sourceName,
      data: mapDraftData(draft.data, fuente.id, url),
      imageUrls: Array.isArray(draft.imageUrls) ? draft.imageUrls : [],
    })
  } catch (error) {
    return NextResponse.json({
      error: error instanceof Error ? error.message : "No se pudo importar la publicación.",
    }, { status: 502 })
  }
}
