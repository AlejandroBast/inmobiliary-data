import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { formatCOP, formatDate, formatNumber } from "@/lib/format"
import {
  BarChart3,
  CalendarClock,
  CircleDollarSign,
  Database,
  Home,
  Layers3,
  MapPinned,
  Tags,
  TrendingUp,
  type LucideIcon,
} from "lucide-react"

type Row = Record<string, any> & { id: number }
type CountItem = { label: string; count: number }

function toNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function toDate(value: unknown) {
  if (!value) return null
  const date = value instanceof Date ? value : new Date(String(value))
  return Number.isNaN(date.getTime()) ? null : date
}

function average(values: Array<number | null>) {
  const valid = values.filter((value): value is number => value !== null)
  return valid.length ? valid.reduce((total, value) => total + value, 0) / valid.length : null
}

function median(values: Array<number | null>) {
  const valid = values.filter((value): value is number => value !== null).sort((a, b) => a - b)
  if (!valid.length) return null
  const middle = Math.floor(valid.length / 2)
  return valid.length % 2 === 0 ? (valid[middle - 1] + valid[middle]) / 2 : valid[middle]
}

function percent(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

function countBy(rows: Row[], key: string, fallback = "Sin dato") {
  const counts = new Map<string, number>()
  rows.forEach((row) => {
    const label = String(row[key] ?? "").trim() || fallback
    counts.set(label, (counts.get(label) ?? 0) + 1)
  })
  return Array.from(counts, ([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count)
}

function priceBucket(precio: number | null) {
  if (precio === null) return "Sin precio"
  if (precio <= 100_000_000) return "Hasta 100M"
  if (precio <= 200_000_000) return "100M a 200M"
  if (precio <= 400_000_000) return "200M a 400M"
  return "Mas de 400M"
}

export function PublicacionesDashboardStats({
  publicaciones,
  totalPublicaciones,
  hasActiveFilters,
}: {
  publicaciones: Row[]
  totalPublicaciones: number
  hasActiveFilters: boolean
}) {
  const visibles = publicaciones.length
  const porcentajeVisible = percent(visibles, totalPublicaciones)
  const precios = publicaciones.map((p) => toNumber(p.precio))
  const precioPromedio = average(precios)
  const precioMedio = median(precios)
  const precioM2Promedio = average(publicaciones.map((p) => toNumber(p.precioM2)))
  const areaPromedio = average(publicaciones.map((p) => toNumber(p.m2)))
  const barrios = countBy(publicaciones, "barrio", "Sin barrio")
  const fuentes = countBy(publicaciones, "fuenteNombre", "Sin fuente")
  const tipos = countBy(publicaciones, "tipoInmueble", "Inmueble")
  const conBarrio = publicaciones.filter((p) => String(p.barrio ?? "").trim()).length
  const conCoordenadas = publicaciones.filter((p) => p.coordenadas || (p.latitud && p.longitud)).length
  const conArea = publicaciones.filter((p) => toNumber(p.m2) !== null).length
  const conPrecioM2 = publicaciones.filter((p) => toNumber(p.precioM2) !== null).length
  const conNotas = publicaciones.filter((p) => String(p.notas ?? "").trim()).length
  const fechas = publicaciones
    .map((p) => toDate(p.fechaCaptura))
    .filter((date): date is Date => date !== null)
    .sort((a, b) => b.getTime() - a.getTime())
  const recientes = fechas.filter((date) => date.getTime() >= Date.now() - 7 * 24 * 60 * 60 * 1000).length
  const preciosPorRango = Array.from(
    publicaciones.reduce((counts, p) => {
      const label = priceBucket(toNumber(p.precio))
      counts.set(label, (counts.get(label) ?? 0) + 1)
      return counts
    }, new Map<string, number>()),
    ([label, count]) => ({ label, count }),
  )
  const publicacionesConPrecio = publicaciones
    .map((p) => ({ publicacion: p, precio: toNumber(p.precio) }))
    .filter((item): item is { publicacion: Row; precio: number } => item.precio !== null)
    .sort((a, b) => a.precio - b.precio)
  const masEconomica = publicacionesConPrecio[0]?.publicacion ?? null
  const masCostosa = publicacionesConPrecio[publicacionesConPrecio.length - 1]?.publicacion ?? null

  return (
    <section className="space-y-4" aria-label="Resumen de publicaciones">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
        <Card className="border-slate-200/70 bg-gradient-to-br from-background via-emerald-50/50 to-slate-50 dark:border-white/10 dark:via-emerald-400/5 dark:to-white/5">
          <CardContent className="grid gap-5 p-5 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{hasActiveFilters ? "Vista filtrada" : "Inventario completo"}</Badge>
                <Badge variant="outline">{formatNumber(visibles)} visibles</Badge>
                <Badge variant="outline">{formatNumber(totalPublicaciones)} totales</Badge>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium text-muted-foreground">Publicaciones disponibles</p>
                <p className="text-4xl font-semibold tracking-tight sm:text-5xl">{formatNumber(visibles)}</p>
                <p className="text-sm text-muted-foreground">
                  {hasActiveFilters
                    ? `${porcentajeVisible}% del inventario coincide con los filtros actuales.`
                    : "Todos los registros cargados estan disponibles para explorar."}
                </p>
              </div>
              <Progress value={porcentajeVisible} />
            </div>
            <div className="grid content-start gap-3 sm:grid-cols-3 md:grid-cols-1">
              <CompactStat icon={TrendingUp} label="Precio promedio" value={formatCOP(precioPromedio)} detail={precioM2Promedio ? `${formatCOP(precioM2Promedio)} por m2` : "Sin precio por m2"} />
              <CompactStat icon={Layers3} label="Area promedio" value={formatNumber(areaPromedio, " m2")} detail={`${formatNumber(conArea)} con area`} />
              <CompactStat icon={CalendarClock} label="Ultima captura" value={fechas[0] ? formatDate(fechas[0]) : "Sin fecha"} detail={`${formatNumber(recientes)} en los ultimos 7 dias`} />
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200/70 dark:border-white/10">
          <CardContent className="grid gap-4 p-5">
            <p className="text-sm font-medium">Lectura rapida</p>
            <CompactStat icon={Home} label="Tipo dominante" value={tipos[0]?.label ?? "Sin datos"} detail={tipos[0] ? `${formatNumber(tipos[0].count)} publicaciones` : "Aun no hay datos"} />
            <CompactStat icon={Database} label="Fuente principal" value={fuentes[0]?.label ?? "Sin fuente"} detail={fuentes[0] ? `${formatNumber(fuentes[0].count)} registros` : "Aun no hay datos"} />
            <CompactStat icon={MapPinned} label="Barrio mas comun" value={barrios[0]?.label ?? "Sin barrio"} detail={barrios[0] ? `${formatNumber(barrios[0].count)} publicaciones` : "Aun no hay datos"} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={Database} label="Cobertura visible" value={`${porcentajeVisible}%`} detail={`${formatNumber(visibles)} de ${formatNumber(totalPublicaciones)} publicaciones`} tone="border-slate-200 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200" />
        <MetricCard icon={CircleDollarSign} label="Precio promedio" value={formatCOP(precioPromedio)} detail={precioMedio ? `${formatCOP(precioMedio)} precio medio` : "Sin datos de precio"} tone="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300" />
        <MetricCard icon={MapPinned} label="Barrios visibles" value={formatNumber(barrios.filter((b) => b.label !== "Sin barrio").length)} detail={`${formatNumber(conCoordenadas)} con coordenadas`} tone="border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-300" />
        <MetricCard icon={Tags} label="Datos con notas" value={`${percent(conNotas, visibles)}%`} detail={`${formatNumber(conNotas)} publicaciones anotadas`} tone="border-slate-200 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200" />
      </div>

      <section id="precios" className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="border-slate-200/70 dark:border-white/10">
          <CardContent className="space-y-4 p-4">
            <div className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                <CircleDollarSign className="size-4" />
              </span>
              <div>
                <p className="text-sm font-medium">Analisis de precios</p>
                <p className="text-xs text-muted-foreground">Lectura rapida para comparables inmobiliarios.</p>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <PriceInsight label="Promedio" value={formatCOP(precioPromedio)} detail={precioM2Promedio ? `${formatCOP(precioM2Promedio)} por m2` : "Sin m2 suficiente"} />
              <PriceInsight label="Precio medio" value={formatCOP(precioMedio)} detail="Reduce el ruido de extremos" />
              <PriceInsight label="Muestra" value={formatNumber(publicacionesConPrecio.length)} detail="Con precio valido" />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <FeaturedListing title="Mas economica" publicacion={masEconomica} />
              <FeaturedListing title="Mas costosa" publicacion={masCostosa} />
            </div>
          </CardContent>
        </Card>
        <DistributionPanel title="Rangos de precio" icon={BarChart3} items={preciosPorRango} total={visibles} />
      </section>

      <div className="grid gap-3 lg:grid-cols-2">
        <div id="barrios">
          <DistributionPanel title="Top barrios" icon={MapPinned} items={barrios.slice(0, 7)} total={visibles} />
        </div>
        <Card id="calidad">
          <CardContent className="space-y-4 p-4">
            <p className="text-sm font-medium">Calidad de datos</p>
            <QualityBar label="Barrio" value={conBarrio} total={visibles} />
            <QualityBar label="Area" value={conArea} total={visibles} />
            <QualityBar label="Precio por m2" value={conPrecioM2} total={visibles} />
            <QualityBar label="Coordenadas" value={conCoordenadas} total={visibles} />
            <QualityBar label="Notas" value={conNotas} total={visibles} />
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function PriceInsight({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{detail}</p>
    </div>
  )
}

function FeaturedListing({ title, publicacion }: { title: string; publicacion: Row | null }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      {publicacion ? (
        <div className="mt-2 space-y-1">
          <p className="font-semibold text-emerald-700 dark:text-emerald-300">{formatCOP(publicacion.precio)}</p>
          <p className="text-sm">{publicacion.tipoInmueble || "Inmueble"} - {publicacion.barrio || "Sin barrio"}</p>
          <p className="text-xs text-muted-foreground">{formatNumber(publicacion.m2, " m2")} - {formatCOP(publicacion.precioM2)} por m2</p>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">Sin datos visibles.</p>
      )}
    </div>
  )
}

function MetricCard({ icon: Icon, label, value, detail, tone }: { icon: LucideIcon; label: string; value: string; detail: string; tone: string }) {
  return (
    <Card className="border-slate-200/70 dark:border-white/10">
      <CardContent className="flex min-h-32 flex-col justify-between gap-4 p-4">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          <span className={`flex size-9 shrink-0 items-center justify-center rounded-md border ${tone}`}>
            <Icon className="size-4" />
          </span>
        </div>
        <div className="space-y-1">
          <p className="text-2xl font-semibold tracking-tight">{value}</p>
          <p className="text-xs text-muted-foreground">{detail}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function CompactStat({ icon: Icon, label, value, detail }: { icon: LucideIcon; label: string; value: string; detail: string }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-semibold">{value}</p>
        <p className="text-xs text-muted-foreground">{detail}</p>
      </div>
    </div>
  )
}

function DistributionPanel({ title, icon: Icon, items, total }: { title: string; icon: LucideIcon; items: CountItem[]; total: number }) {
  return (
    <Card className="border-slate-200/70 dark:border-white/10">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-md bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300">
            <Icon className="size-4" />
          </span>
          <p className="text-sm font-medium">{title}</p>
        </div>
        <div className="space-y-3">
          {items.length ? items.map((item) => <BarRow key={item.label} label={item.label} value={item.count} total={total} />) : <p className="text-sm text-muted-foreground">Sin datos visibles.</p>}
        </div>
      </CardContent>
    </Card>
  )
}

function BarRow({ label, value, total }: { label: string; value: number; total: number }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="truncate font-medium">{label}</span>
        <span className="shrink-0 text-muted-foreground">{formatNumber(value)}</span>
      </div>
      <Progress value={percent(value, total)} />
    </div>
  )
}

function QualityBar({ label, value, total }: { label: string; value: number; total: number }) {
  const progress = percent(value, total)
  const tone =
    progress >= 75
      ? "bg-emerald-500"
      : progress >= 45
      ? "bg-amber-500"
      : "bg-rose-500"

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">{progress}%</span>
      </div>
      <Progress value={progress} tone={tone} />
    </div>
  )
}

function Progress({ value, tone = "bg-primary/80" }: { value: number; tone?: string }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(value, 100)}%` }} />
    </div>
  )
}
