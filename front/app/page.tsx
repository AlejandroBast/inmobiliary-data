import {
  getBarrios,
  getCoincidenciasPublicaciones,
  getFuentes,
  getPhNombres,
  getPublicaciones,
  getTiposInmueble,
  type PublicacionFilters,
} from "@/app/actions/publicaciones"
import { AppShell } from "@/components/app-shell"
import { PublicacionesDataLayout } from "@/components/publicaciones-data-layout"
import { PublicacionesManagerPro } from "@/components/publicaciones-manager-pro"
import { PublicacionesFiltrosPro } from "@/components/publicaciones-filtros-pro"
import { ScraperControlPanel } from "@/components/scraper-control-panel"
import { buttonVariants } from "@/components/ui/button"
import { Building2, Download, LayoutDashboard } from "lucide-react"
import Link from "next/link"

export const dynamic = "force-dynamic"

function firstValue(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value[0] ?? ""
  }

  return value ?? ""
}

function allValues(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value : value ? [value] : []
  return raw.map((item) => item.trim()).filter(Boolean)
}

function hasActiveFilters(filters: PublicacionFilters) {
  return Object.values(filters).some((value) => String(value ?? "").trim() !== "")
}

function activeFilterCount(filters: PublicacionFilters) {
  return Object.values(filters).filter((value) => String(value ?? "").trim() !== "").length
}

function buildSearchString(params: Record<string, string | string[] | undefined>) {
  const search = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => item && search.append(key, item))
      return
    }

    if (value) search.set(key, value)
  })

  return search.toString()
}

export default async function Page({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}) {
  const params = (await searchParams) ?? {}

  const tipoInmuebleValues = allValues(params.tipoInmueble)
  const phTipoValues = allValues(params.phTipo)
  const barrioValues = allValues(params.barrio).length ? allValues(params.barrio) : allValues(params.ubicacion)

  const filtros: PublicacionFilters = {
    id: firstValue(params.id),
    tipoInmueble: tipoInmuebleValues,
    fuenteId: firstValue(params.fuenteId),
    fecha: firstValue(params.fecha),
    habitaciones: firstValue(params.habitaciones),
    banios: firstValue(params.banios),
    barrio: barrioValues,
    precioMin: firstValue(params.precioMin),
    precioMax: firstValue(params.precioMax),
    m2Min: firstValue(params.m2Min),
    m2Max: firstValue(params.m2Max),
    phTipo: phTipoValues,
    parqueadero: firstValue(params.parqueadero),
    duplicados: firstValue(params.duplicados),
  }

  const [publicaciones, fuentes, barriosData, tiposInmueble, phData] = await Promise.all([
    getPublicaciones(filtros),
    getFuentes(),
    getBarrios(),
    getTiposInmueble(),
    getPhNombres(),
  ])
  const coincidencias = await getCoincidenciasPublicaciones(publicaciones.map((publicacion) => publicacion.id))
  const publicacionesConCoincidencias = publicaciones.map((publicacion) => ({
    ...publicacion,
    coincidencias: coincidencias[publicacion.id] ?? [],
  }))

  const filtrosActivos = hasActiveFilters(filtros)
  const totalFiltrosActivos = activeFilterCount(filtros)
  const dashboardSearch = buildSearchString(params)
  const dashboardHref = dashboardSearch ? `/dashboard?${dashboardSearch}` : "/dashboard"

  return (
    <AppShell
      active="publicaciones"
      title="Publicaciones inmobiliarias"
      subtitle="Gestiona el inventario capturado y revisa comparables por precio, barrio y fuente."
      icon={<Building2 className="size-5" />}
      actions={
        <>
          <a href="/api/export/database" className={buttonVariants({ variant: "outline", size: "lg", className: "gap-2 border-slate-200 text-slate-700 hover:bg-slate-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-white/5" })}>
            <Download className="size-4" />
            Exportar Excel
          </a>
          <Link href={dashboardHref} className={buttonVariants({ variant: "outline", size: "lg", className: "gap-2 border-emerald-200 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-400/30 dark:text-emerald-300 dark:hover:bg-emerald-400/10" })}>
            <LayoutDashboard className="size-4" />
            Ver dashboard
          </Link>
        </>
      }
    >
      <ScraperControlPanel />
      <PublicacionesDataLayout
        activeFilterCount={totalFiltrosActivos}
        filterPanel={
          <PublicacionesFiltrosPro
            fuentes={fuentes}
            barrios={barriosData.barrios}
            tiposInmueble={tiposInmueble}
            phNombres={phData.ph}
            hasSinBarrio={barriosData.hasSinBarrio}
            hasSinPh={phData.hasSinPh}
            initialValues={{
              id: filtros.id ?? undefined,
              tipoInmueble: tipoInmuebleValues,
              fuenteId: filtros.fuenteId ?? undefined,
              fecha: filtros.fecha ?? undefined,
              habitaciones: filtros.habitaciones ?? undefined,
              banios: filtros.banios ?? undefined,
              barrio: barrioValues,
              precioMin: filtros.precioMin ?? undefined,
              precioMax: filtros.precioMax ?? undefined,
              m2Min: filtros.m2Min ?? undefined,
              m2Max: filtros.m2Max ?? undefined,
              phTipo: phTipoValues,
              parqueadero: filtros.parqueadero ?? undefined,
              duplicados: filtros.duplicados ?? undefined,
            }}
          />
        }
      >
        <section id="publicaciones" className="min-w-0">
          <PublicacionesManagerPro
            publicaciones={publicacionesConCoincidencias}
            fuentes={fuentes}
            barrios={barriosData.barrios}
            tiposInmueble={tiposInmueble}
            phNombres={phData.ph}
            hasSinBarrio={barriosData.hasSinBarrio}
            hasSinPh={phData.hasSinPh}
            hasActiveFilters={filtrosActivos}
          />
        </section>
      </PublicacionesDataLayout>
    </AppShell>
  )
}
