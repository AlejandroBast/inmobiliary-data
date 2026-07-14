import {
  cancelScraper,
  getScraperJobs,
  isScraperSource,
  SCRAPER_SOURCES,
  startScraper,
} from "@/lib/scrapers"
import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"
export const runtime = "nodejs"

export async function GET() {
  return NextResponse.json({ jobs: getScraperJobs(), sources: SCRAPER_SOURCES })
}

export async function POST(request: Request) {
  let body: unknown

  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: "Solicitud inválida" }, { status: 400 })
  }

  const sourceId = (body as { sourceId?: unknown })?.sourceId
  if (!isScraperSource(sourceId)) {
    return NextResponse.json({ error: "Fuente no permitida" }, { status: 400 })
  }

  const existing = getScraperJobs().find((job) => job.sourceId === sourceId)
  if (existing?.state === "running" || existing?.state === "cancelling") {
    return NextResponse.json({ error: "Esta fuente todavía está ejecutándose o cerrándose", job: existing }, { status: 409 })
  }

  return NextResponse.json({ job: startScraper(sourceId) }, { status: 202 })
}

export async function DELETE(request: Request) {
  let body: unknown

  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: "Solicitud inválida" }, { status: 400 })
  }

  const sourceId = (body as { sourceId?: unknown })?.sourceId
  if (!isScraperSource(sourceId)) {
    return NextResponse.json({ error: "Fuente no permitida" }, { status: 400 })
  }

  if (!(await cancelScraper(sourceId))) {
    return NextResponse.json({ error: "No hay un escaneo activo para esta fuente" }, { status: 409 })
  }

  const job = getScraperJobs().find((item) => item.sourceId === sourceId)
  return NextResponse.json({ job })
}
