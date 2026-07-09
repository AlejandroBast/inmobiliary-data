import {
  getBarrios,
  getFuentes,
  getPublicaciones,
  type PublicacionFilters,
} from "@/app/actions/publicaciones"
import { AppShell } from "@/components/app-shell"
import { PublicacionesDataLayout } from "@/components/publicaciones-data-layout"
import { PublicacionesManagerPro } from "@/components/publicaciones-manager-pro"
import { PublicacionesFiltrosPro } from "@/components/publicaciones-filtros-pro"
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

  const filtros: PublicacionFilters = {
    id: firstValue(params.id),
    tipoInmueble: firstValue(params.tipoInmueble),
    fuenteId: firstValue(params.fuenteId),
    fecha: firstValue(params.fecha),
    habitaciones: firstValue(params.habitaciones),
    banios: firstValue(params.banios),
    barrio: firstValue(params.barrio) || firstValue(params.ubicacion),
    precioMin: firstValue(params.precioMin),
    precioMax: firstValue(params.precioMax),
    m2Min: firstValue(params.m2Min),
    m2Max: firstValue(params.m2Max),
    phTipo: firstValue(params.phTipo),
    parqueadero: firstValue(params.parqueadero),
  }

  const [publicaciones, fuentes, barriosData] = await Promise.all([
    getPublicaciones(filtros),
    getFuentes(),
    getBarrios(),
  ])

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
      <PublicacionesDataLayout
        activeFilterCount={totalFiltrosActivos}
        filterPanel={
          <PublicacionesFiltrosPro
            fuentes={fuentes}
            barrios={barriosData.barrios}
            hasSinBarrio={barriosData.hasSinBarrio}
            initialValues={{
              id: filtros.id ?? undefined,
              tipoInmueble: filtros.tipoInmueble ?? undefined,
              fuenteId: filtros.fuenteId ?? undefined,
              fecha: filtros.fecha ?? undefined,
              habitaciones: filtros.habitaciones ?? undefined,
              banios: filtros.banios ?? undefined,
              barrio: filtros.barrio ?? undefined,
              precioMin: filtros.precioMin ?? undefined,
              precioMax: filtros.precioMax ?? undefined,
              m2Min: filtros.m2Min ?? undefined,
              m2Max: filtros.m2Max ?? undefined,
              phTipo: filtros.phTipo ?? undefined,
              parqueadero: filtros.parqueadero ?? undefined,
            }}
          />
        }
      >
        <section id="publicaciones" className="min-w-0">
          <PublicacionesManagerPro
            publicaciones={publicaciones}
            fuentes={fuentes}
            hasActiveFilters={filtrosActivos}
          />
        </section>
      </PublicacionesDataLayout>
    </AppShell>
  )
}
