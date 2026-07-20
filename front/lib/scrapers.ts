import "server-only"

import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import path from "node:path"

// Los scrapers son modulos del paquete inmobiliary (src/inmobiliary/scrapers/)
// y se ejecutan con "python -m", no por ruta de archivo. Se guarda tambien la
// ruta del archivo solo para verificar que exista antes de lanzar el proceso.
export const SCRAPER_SOURCES = {
  fincaraiz: { name: "Finca Raiz", module: "inmobiliary.scrapers.fincaraiz", file: "src/inmobiliary/scrapers/fincaraiz.py", estimatedSeconds: 600 },
  ciencuadras: { name: "Ciencuadras", module: "inmobiliary.scrapers.ciencuadras", file: "src/inmobiliary/scrapers/ciencuadras.py", estimatedSeconds: 600 },
  metrocuadrado: { name: "Metrocuadrado", module: "inmobiliary.scrapers.metrocuadrado", file: "src/inmobiliary/scrapers/metrocuadrado.py", estimatedSeconds: 720 },
  amorel: { name: "Amorel", module: "inmobiliary.scrapers.amorel", file: "src/inmobiliary/scrapers/amorel.py", estimatedSeconds: 900 },
  facebook: { name: "Facebook Marketplace", module: "inmobiliary.scrapers.facebook", file: "src/inmobiliary/scrapers/facebook.py", estimatedSeconds: 600 },
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

function splitCommand(value: string) {
  const parts = value.match(/"[^"]+"|'[^']+'|\S+/g)?.map((part) => part.replace(/^["']|["']$/g, "")) ?? []
  return { command: parts[0] ?? value, args: parts.slice(1) }
}

function resolvePythonCommand() {
  const configured = process.env.SCRAPER_PYTHON?.trim()
  if (configured) return splitCommand(configured)

  if (process.platform === "win32") {
    return { command: "py", args: ["-3"] }
  }

  return { command: "python3", args: [] }
}

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
  const python = resolvePythonCommand()
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

  if (!existsSync(scriptPath)) {
    job.state = "error"
    job.finishedAt = new Date().toISOString()
    job.message = `No existe el script ${source.file}`
    job.progress = 100
    job.remainingSeconds = 0
    appendOutput(job, `Ruta esperada: ${scriptPath}`)
    return job
  }

  try {
    // "-m modulo" en vez de la ruta: ejecutar el archivo directo rompe los
    // imports absolutos del paquete. PYTHONPATH=src evita depender de que el
    // paquete este instalado con pip install -e .
    const spawnArgs = [...python.args, "-m", source.module]
    appendOutput(job, `Ejecutando: ${[python.command, ...spawnArgs].join(" ")}`)
    const child = spawn(python.command, spawnArgs, {
      cwd: projectDir,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: [path.join(projectDir, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      },
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
        : code === 9009
          ? "No se encontro Python para ejecutar el scraper"
          : `El escaneo termino con codigo ${code ?? "desconocido"}`
      if (code === 9009) {
        appendOutput(job, "En Windows el codigo 9009 significa que no se encontro el comando. Reinicia el front o define SCRAPER_PYTHON.")
      }
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
