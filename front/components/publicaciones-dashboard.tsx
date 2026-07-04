import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { formatCOP, formatNumber } from "@/lib/format"
import { BarChart3, Building2, CircleDollarSign, Tags, TrendingUp } from "lucide-react"
import type { ComponentType } from "react"

type Row = Record<string, any> & { id: number }

type SummaryItem = {
  label: string
  value: string
  helper: string
  icon: ComponentType<{ className?: string }>
}

function toNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function average(values: Array<number | null>) {
  const valid = values.filter((value): value is number => value !== null)
  if (valid.length === 0) return null
  return valid.reduce((sum, value) => sum + value, 0) / valid.length
}

function topGroups(rows: Row[], key: keyof Row, fallback: string, limit = 5) {
  const counts = new Map<string, number>()

  for (const row of rows) {
    const raw = row[key]
    const label = typeof raw === "string" ? raw.trim() : String(raw ?? "").trim()
    counts.set(label || fallback, (counts.get(label || fallback) ?? 0) + 1)
  }

  return Array.from(counts, ([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "es"))
    .slice(0, limit)
}

function dateWithinDays(value: unknown, days: number) {
  if (!value) return false
  const date = value instanceof Date ? value : new Date(String(value))
  if (Number.isNaN(date.getTime())) return false

  const threshold = new Date()
  threshold.setDate(threshold.getDate() - days)
  return date >= threshold
}

function GroupBars({
  title,
  items,
  total,
}: {
  title: string
  items: Array<{ label: string; count: number }>
  total: number
}) {
  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium">{title}</h2>
          <Badge variant="secondary">{items.length}</Badge>
        </div>
        <div className="space-y-3">
          {items.length > 0 ? (
            items.map((item) => {
              const percent = total > 0 ? Math.max((item.count / total) * 100, 3) : 0

              return (
                <div key={item.label} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate text-muted-foreground">{item.label}</span>
                    <span className="shrink-0 font-medium">{item.count}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
                  </div>
                </div>
              )
            })
          ) : (
            <p className="text-sm text-muted-foreground">Sin datos para mostrar.</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function PublicacionesDashboard({
  publicaciones,
  hasActiveFilters,
  activeFilters,
}: {
  publicaciones: Row[]
  hasActiveFilters: boolean
  activeFilters: string[]
}) {
  const total = publicaciones.length
  const precios = publicaciones.map((row) => toNumber(row.precio))
  const areas = publicaciones.map((row) => toNumber(row.m2))
  const precioPromedio = average(precios)
  const areaPromedio = average(areas)
  const recientes = publicaciones.filter((row) => dateWithinDays(row.fechaCaptura, 7)).length
  const conNotas = publicaciones.filter((row) => String(row.notas ?? "").trim() !== "").length
  const fuentes = topGroups(publicaciones, "fuenteNombre", "Sin fuente")
  const tipos = topGroups(publicaciones, "tipoInmueble", "Sin tipo")
  const barrios = topGroups(publicaciones, "barrio", "Sin barrio")

  const summary: SummaryItem[] = [
    {
      label: "Precio promedio",
      value: formatCOP(precioPromedio),
      helper: "Segun publicaciones encontradas",
      icon: CircleDollarSign,
    },
    {
      label: "Area promedio",
      value: formatNumber(areaPromedio, " m2"),
      helper: "Solo registros encontrados con area",
      icon: TrendingUp,
    },
    {
      label: "Capturas recientes",
      value: formatNumber(recientes),
      helper: "Encontradas en los ultimos 7 dias",
      icon: BarChart3,
    },
  ]

  return (
    <section className="space-y-4" aria-label="Dashboard de publicaciones">
      <Card>
        <CardContent className="grid gap-4 p-5 lg:grid-cols-[1fr_auto] lg:items-center">
          <div className="flex items-start gap-4">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Building2 className="size-5" />
            </div>
            <div className="min-w-0 space-y-2">
              <div>
                <p className="text-sm text-muted-foreground">
                  {hasActiveFilters ? "Publicaciones encontradas con los filtros" : "Publicaciones disponibles"}
                </p>
                <p className="text-4xl font-semibold tracking-tight">{formatNumber(total)}</p>
              </div>
              <p className="max-w-2xl text-sm text-muted-foreground">
                {hasActiveFilters
                  ? "Este total se calcula con los mismos resultados que aparecen en la tabla."
                  : "Este total muestra todo el inventario disponible antes de aplicar filtros."}
              </p>
            </div>
          </div>

          {hasActiveFilters && (
            <div className="flex flex-wrap gap-2 lg:max-w-md lg:justify-end">
              {activeFilters.map((filter) => (
                <Badge key={filter} variant="secondary">
                  {filter}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        {summary.map((item) => {
          const Icon = item.icon

          return (
            <Card key={item.label}>
              <CardContent className="flex items-start justify-between gap-3 p-4">
                <div className="min-w-0 space-y-1">
                  <p className="text-sm text-muted-foreground">{item.label}</p>
                  <p className="truncate text-2xl font-semibold tracking-tight">{item.value}</p>
                  <p className="text-xs text-muted-foreground">{item.helper}</p>
                </div>
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <Icon className="size-4 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr]">
        <GroupBars title="Fuentes principales" items={fuentes} total={total} />
        <GroupBars title="Tipos de inmueble" items={tipos} total={total} />
        <GroupBars title="Barrios principales" items={barrios} total={total} />
      </div>

      <div className="grid gap-3">
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-lg bg-muted">
                <Tags className="size-4 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-medium">Publicaciones con notas</p>
                <p className="text-xs text-muted-foreground">Observaciones internas registradas</p>
              </div>
            </div>
            <p className="text-2xl font-semibold">{formatNumber(conNotas)}</p>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
