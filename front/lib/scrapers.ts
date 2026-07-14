import "server-only"

import { spawn } from "node:child_process"
import path from "node:path"

export const SCRAPER_SOURCES = {
  fincaraiz: { name: "Finca Raiz", file: "scraper_fincaraiz_pasto.py", estimatedSeconds: 600 },
  ciencuadras: { name: "Ciencuadras", file: "scraper_ciencuadras.py", estimatedSeconds: 600 },
  metrocuadrado: { name: "Metrocuadrado", file: "scraper_metrocuadrado_pasto.py", estimatedSeconds: 720 },
  amorel: { name: "Amorel", file: "scraper_amorel_pasto.py", estimatedSeconds: 900 },
  facebook: { name: "Facebook Marketplace", file: "scraper_facebook_marketplace.py", estimatedSeconds: 600 },
} as const

export type ScraperSourceId = keyof typeof SCRAPER_SOURCES
export type ScraperState = "idle" | "running" | "cancelling" | "success" | "error"

export type ScraperJob = {
  sourceId: ScraperSourceId
  state: ScraperState
  startedAt: string | null
  finishedAt: string | null
  exitCode: number | null
  message: string
  output: string[]
  progress: number
  elapsedSeconds: number
  remainingSeconds: number | null
  processId: number | null
}

type ScraperStore = Partial<Record<ScraperSourceId, ScraperJob>>

const globalForScrapers = globalThis as typeof globalThis & {
  scraperJobs?: ScraperStore
  scraperProcesses?: Partial<Record<ScraperSourceId, ReturnType<typeof spawn>>>
}

const jobs = globalForScrapers.scraperJobs ?? {}
const processes = globalForScrapers.scraperProcesses ?? {}
globalForScrapers.scraperJobs = jobs
globalForScrapers.scraperProcesses = processes

function idleJob(sourceId: ScraperSourceId): ScraperJob {
  return {
    sourceId,
    state: "idle",
    startedAt: null,
    finishedAt: null,
    exitCode: null,
    message: "Listo para escanear",
    output: [],
    progress: 0,
    elapsedSeconds: 0,
    remainingSeconds: null,
    processId: null,
  }
}

export function isScraperSource(value: unknown): value is ScraperSourceId {
  return typeof value === "string" && value in SCRAPER_SOURCES
}

export function getScraperJobs() {
  return Object.keys(SCRAPER_SOURCES).map((sourceId) => {
    const id = sourceId as ScraperSourceId
    const job = jobs[id] ?? idleJob(id)
    if (job.state !== "running" || !job.startedAt) return job

    const elapsedSeconds = Math.max(0, Math.floor((Date.now() - new Date(job.startedAt).getTime()) / 1000))
    const estimate = SCRAPER_SOURCES[id].estimatedSeconds
    const progress = Math.min(95, Math.max(2, Math.round((elapsedSeconds / estimate) * 100)))
    return {
      ...job,
      elapsedSeconds,
      progress,
      remainingSeconds: Math.max(0, estimate - elapsedSeconds),
    }
  })
}

function appendOutput(job: ScraperJob, chunk: Buffer | string) {
  const lines = chunk
    .toString()
    .replace(/\r/g, "")
    .split("\n")
    .filter(Boolean)

  job.output = [...job.output, ...lines].slice(-120)
}

export function startScraper(sourceId: ScraperSourceId) {
  const current = jobs[sourceId]
  if (current?.state === "running") return current

  const source = SCRAPER_SOURCES[sourceId]
  const projectDir = path.resolve(process.cwd(), "..")
  const scriptPath = path.join(projectDir, source.file)
  const python = process.env.SCRAPER_PYTHON?.trim() || "python"
  const job: ScraperJob = {
    sourceId,
    state: "running",
    startedAt: new Date().toISOString(),
    finishedAt: null,
    exitCode: null,
    message: `Escaneando ${source.name}...`,
    output: [],
    progress: 2,
    elapsedSeconds: 0,
    remainingSeconds: source.estimatedSeconds,
    processId: null,
  }

  jobs[sourceId] = job

  try {
    const child = spawn(python, [scriptPath], {
      cwd: projectDir,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      windowsHide: true,
    })
    processes[sourceId] = child
    job.processId = child.pid ?? null

    child.stdout.on("data", (chunk) => appendOutput(job, chunk))
    child.stderr.on("data", (chunk) => appendOutput(job, chunk))
    child.on("error", (error) => {
      if (jobs[sourceId] !== job) return
      job.state = "error"
      job.finishedAt = new Date().toISOString()
      job.message = `No se pudo iniciar: ${error.message}`
      appendOutput(job, error.message)
    })
    child.on("close", (code) => {
      if (processes[sourceId] === child) delete processes[sourceId]
      if (jobs[sourceId] !== job) return
      job.exitCode = code
      job.finishedAt = new Date().toISOString()
      job.state = code === 0 ? "success" : "error"
      job.progress = 100
      job.remainingSeconds = 0
      if (job.startedAt) {
        job.elapsedSeconds = Math.max(0, Math.floor((Date.now() - new Date(job.startedAt).getTime()) / 1000))
      }
      job.message = code === 0
        ? `Escaneo de ${source.name} terminado`
        : `El escaneo terminó con código ${code ?? "desconocido"}`
    })
  } catch (error) {
    job.state = "error"
    job.finishedAt = new Date().toISOString()
    job.message = error instanceof Error ? error.message : "No se pudo iniciar el scraper"
  }

  return job
}

export async function cancelScraper(sourceId: ScraperSourceId) {
  const job = jobs[sourceId]
  const child = processes[sourceId]
  if (!job) return false
  if (job.state === "error" && !child) {
    jobs[sourceId] = idleJob(sourceId)
    return true
  }
  if (job.state !== "running") return false

  const processId = child?.pid ?? job.processId
  if (!processId) {
    // Trabajo huérfano de una versión anterior del servidor: no existe una
    // referencia ni PID que detener, por lo que se desbloquea la interfaz.
    jobs[sourceId] = idleJob(sourceId)
    return true
  }

  // Un objeto distinto evita que el evento close del proceso cancelado cambie
  // el estado a completado o error mientras esperamos a que Windows lo cierre.
  jobs[sourceId] = {
    ...job,
    state: "cancelling",
    message: "Cancelando escaneo y cerrando el navegador...",
  }

  if (process.platform === "win32") {
    await new Promise<void>((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(processId), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      })
      killer.once("close", () => resolve())
      killer.once("error", () => {
        child?.kill()
        resolve()
      })
    })
  } else {
    if (!child) {
      jobs[sourceId] = idleJob(sourceId)
      return true
    }
    child.kill("SIGTERM")
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(resolve, 5000)
      child.once("close", () => {
        clearTimeout(timeout)
        resolve()
      })
    })
  }

  if (processes[sourceId] === child) delete processes[sourceId]
  jobs[sourceId] = idleJob(sourceId)
  return true
}
