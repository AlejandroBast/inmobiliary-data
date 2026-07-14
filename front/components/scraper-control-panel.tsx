"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { CheckCircle2, CircleAlert, Clock3, LoaderCircle, Play, Radar, Square } from "lucide-react"
import { useRouter } from "next/navigation"
import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

type SourceId = "fincaraiz" | "ciencuadras" | "metrocuadrado" | "amorel" | "facebook"
type Job = {
  sourceId: SourceId
  state: "idle" | "running" | "cancelling" | "success" | "error"
  startedAt: string | null
  finishedAt: string | null
  message: string
  output: string[]
  progress: number
  elapsedSeconds: number
  remainingSeconds: number | null
  processId: number | null
}

function formatDuration(totalSeconds: number | null) {
  if (totalSeconds === null) return "Calculando..."
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0 ? `${minutes} min ${String(seconds).padStart(2, "0")} s` : `${seconds} s`
}

const sources: Array<{ id: SourceId; name: string; detail: string }> = [
  { id: "fincaraiz", name: "Finca Raiz", detail: "Inmuebles publicados en Pasto" },
  { id: "ciencuadras", name: "Ciencuadras", detail: "Oferta inmobiliaria de la ciudad" },
  { id: "metrocuadrado", name: "Metrocuadrado", detail: "Propiedades en venta en Pasto" },
  { id: "amorel", name: "Amorel", detail: "Inventario de la inmobiliaria" },
  { id: "facebook", name: "Facebook Marketplace", detail: "Anuncios públicos disponibles" },
]

export function ScraperControlPanel() {
  const router = useRouter()
  const [jobs, setJobs] = useState<Partial<Record<SourceId, Job>>>({})
  const [loading, setLoading] = useState(true)
  const lastPublicationsRefresh = useRef(0)
  const hadActiveScan = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/scrapers", { cache: "no-store" })
      const data = (await response.json()) as { jobs: Job[] }
      setJobs(Object.fromEntries(data.jobs.map((job) => [job.sourceId, job])))

      const hasActiveScan = data.jobs.some((job) => job.state === "running" || job.state === "cancelling")
      const now = Date.now()
      const scanJustFinished = hadActiveScan.current && !hasActiveScan

      // router.refresh actualiza los Server Components y la tabla sin recargar
      // la pestaña ni perder el estado local de los componentes cliente.
      if (scanJustFinished || (hasActiveScan && now - lastPublicationsRefresh.current >= 4000)) {
        lastPublicationsRefresh.current = now
        router.refresh()
      }
      hadActiveScan.current = hasActiveScan
    } catch {
      // Se conserva el último estado visible si falla un sondeo puntual.
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2500)
    return () => window.clearInterval(timer)
  }, [refresh])

  async function run(sourceId: SourceId) {
    setJobs((current) => ({
      ...current,
      [sourceId]: { sourceId, state: "running", startedAt: new Date().toISOString(), finishedAt: null, message: "Iniciando escaneo...", output: [], progress: 2, elapsedSeconds: 0, remainingSeconds: null, processId: null },
    }))

    try {
      const response = await fetch("/api/scrapers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceId }),
      })
      const data = (await response.json()) as { error?: string; job?: Job }
      if (!response.ok) throw new Error(data.error || "No fue posible iniciar el escaneo")
      if (data.job) setJobs((current) => ({ ...current, [sourceId]: data.job }))
      toast.success("Escaneo iniciado", { description: "Puedes seguir trabajando mientras se procesa la fuente." })
    } catch (error) {
      toast.error("No se pudo iniciar", { description: error instanceof Error ? error.message : "Error desconocido" })
      await refresh()
    }
  }

  async function cancel(sourceId: SourceId, sourceName: string) {
    if (!window.confirm(`¿Cancelar el escaneo de ${sourceName}? El progreso actual se perderá.`)) return

    try {
      const response = await fetch("/api/scrapers", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceId }),
      })
      const data = (await response.json()) as { error?: string; job?: Job }
      if (!response.ok) throw new Error(data.error || "No fue posible cancelar el escaneo")
      if (data.job) setJobs((current) => ({ ...current, [sourceId]: data.job }))
      toast.success("Escaneo cancelado", { description: `${sourceName} volvió al estado inicial.` })
    } catch (error) {
      toast.error("No se pudo cancelar", { description: error instanceof Error ? error.message : "Error desconocido" })
      await refresh()
    }
  }

  const runningCount = Object.values(jobs).filter((job) => job?.state === "running").length

  return (
    <Card className="border-emerald-200/80 shadow-sm dark:border-emerald-400/20">
      <CardHeader className="gap-2 border-b bg-emerald-50/60 dark:bg-emerald-400/5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base"><Radar className="size-5 text-emerald-600" />Escanear fuentes</CardTitle>
            <CardDescription>Selecciona el portal que deseas actualizar. Cada proceso se ejecuta de forma independiente.</CardDescription>
          </div>
          {runningCount > 0 && <Badge className="gap-1.5"><LoaderCircle className="size-3 animate-spin" />{runningCount} en ejecución</Badge>}
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 pt-5 sm:grid-cols-2 xl:grid-cols-5">
        {sources.map((source) => {
          const job = jobs[source.id]
          const running = job?.state === "running"
          const cancelling = job?.state === "cancelling"
          const success = job?.state === "success"
          const failed = job?.state === "error"
          const recentOutput = job?.output?.slice(-3) ?? []

          return (
            <div
              key={source.id}
              className={`flex min-h-60 flex-col rounded-2xl border bg-background p-5 transition-all duration-300 ${
                running || cancelling
                  ? "border-emerald-400/70 shadow-[0_0_0_1px_rgba(16,185,129,0.08),0_10px_30px_-18px_rgba(16,185,129,0.65)] dark:border-emerald-400/50 dark:shadow-[0_0_24px_-12px_rgba(52,211,153,0.55)]"
                  : "border-slate-200 shadow-sm hover:border-slate-300 hover:shadow-md dark:border-white/10 dark:hover:border-white/20"
              }`}
            >
              <div className="flex items-start gap-3">
                <div className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full ${running || cancelling || success ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300" : failed ? "bg-red-50 text-destructive dark:bg-red-400/10" : "bg-slate-100 text-slate-500 dark:bg-white/10 dark:text-slate-400"}`}>
                  {running || cancelling ? <LoaderCircle className="size-4 animate-spin" /> : success ? <CheckCircle2 className="size-4" /> : failed ? <CircleAlert className="size-4" /> : <Clock3 className="size-4" />}
                </div>
                <div className="min-w-0">
                  <h3 className="font-semibold leading-6 text-slate-900 dark:text-slate-100">{source.name}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{source.detail}</p>
                </div>
              </div>
              <p className="mt-5 line-clamp-2 min-h-8 text-xs font-medium text-muted-foreground">{loading ? "Consultando estado..." : job?.message || "Listo para escanear"}</p>
              {recentOutput.length > 0 && (
                <pre className="mt-3 max-h-20 overflow-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-2 text-[11px] leading-relaxed text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                  {recentOutput.join("\n")}
                </pre>
              )}
              {(running || cancelling) && <div className="mt-4 space-y-2.5">
                <div className="relative h-2.5 overflow-hidden rounded-full bg-slate-100 ring-1 ring-inset ring-slate-200/70 dark:bg-white/10 dark:ring-white/5" role="progressbar" aria-label={`Progreso de ${source.name}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job?.progress ?? 0}>
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-[width,background-color] duration-700 ease-out"
                    style={{ width: `${job?.progress ?? 0}%` }}
                  />
                </div>
                <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>{job?.progress ?? 0}%</span>
                  {cancelling ? <span>Cerrando proceso...</span> : <span>Restante aprox. {formatDuration(job?.remainingSeconds ?? null)}</span>}
                </div>
                {running && <p className="text-[11px] text-muted-foreground">Transcurrido exacto: {formatDuration(job?.elapsedSeconds ?? 0)}</p>}
              </div>}
              {running || cancelling ? (
                <Button className="mt-auto w-full gap-2 border-red-200 text-red-600 hover:border-red-300 hover:bg-red-50 hover:text-red-700 dark:border-red-400/30 dark:text-red-300 dark:hover:bg-red-400/10" variant="outline" disabled={cancelling} onClick={() => void cancel(source.id, source.name)}>
                  {cancelling ? <LoaderCircle className="size-3.5 animate-spin" /> : <Square className="size-3.5 fill-current" />}
                  {cancelling ? "Cancelando..." : "Cancelar escaneo"}
                </Button>
              ) : (
                <Button className="mt-auto w-full gap-2" variant={failed ? "outline" : "default"} disabled={loading} onClick={() => void run(source.id)}>
                  <Play />
                  {failed ? "Reintentar" : "Escanear"}
                </Button>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
