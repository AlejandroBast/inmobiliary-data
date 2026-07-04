import { getBarrios, getFuentes, getPublicaciones, type PublicacionFilters } from "@/app/actions/publicaciones"
import { PublicacionesDashboard } from "@/components/publicaciones-dashboard"
import { PublicacionesManager } from "@/components/publicaciones-manager"
import { PublicacionesFiltros } from "@/components/publicaciones-filtros"
import { ThemeToggle } from "@/components/theme-toggle"
import { Building2 } from "lucide-react"

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

function numericFilterLabel(value: string | null | undefined, singular: string, plural: string) {
  const cleanValue = String(value ?? "").trim()
  if (!cleanValue) return null
  if (cleanValue.endsWith("+")) return `${plural}: ${cleanValue.replace("+", " o mas")}`
  return `${Number(cleanValue) === 1 ? singular : plural}: ${cleanValue}`
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
    parqueadero: firstValue(params.parqueadero),
  }

  const [publicaciones, fuentes, barriosData] = await Promise.all([
    getPublicaciones(filtros),
    getFuentes(),
    getBarrios(),
  ])
  const filtersActive = hasActiveFilters(filtros)
  const fuenteActiva = fuentes.find((fuente) => String(fuente.id) === String(filtros.fuenteId ?? ""))
  const barrioActivo =
    filtros.barrio === "__sin_barrio"
      ? "Sin barrio"
      : barriosData.barrios.find((barrio) => barrio.value === filtros.barrio)?.label

  const activeFilters = [
    filtros.id ? `ID: ${filtros.id}` : null,
    filtros.tipoInmueble ? `Tipo: ${filtros.tipoInmueble}` : null,
    filtros.fuenteId ? `Fuente: ${fuenteActiva?.nombre ?? filtros.fuenteId}` : null,
    filtros.fecha ? `Fecha: ${filtros.fecha}` : null,
    numericFilterLabel(filtros.habitaciones, "Habitacion", "Habitaciones"),
    numericFilterLabel(filtros.banios, "Bano", "Banos"),
    numericFilterLabel(filtros.parqueadero, "Parqueadero", "Parqueaderos"),
    filtros.barrio ? `Barrio: ${barrioActivo ?? filtros.barrio}` : null,
    filtros.precioMin ? `Precio desde: ${filtros.precioMin}` : null,
    filtros.precioMax ? `Precio hasta: ${filtros.precioMax}` : null,
  ].filter((filter): filter is string => Boolean(filter))

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Building2 className="size-6" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-balance">
              Publicaciones inmobiliarias
            </h1>
            <p className="text-sm text-muted-foreground">
              Gestiona el inventario de inmuebles capturados: crear, ver, editar y eliminar.
            </p>
          </div>
        </div>
        <ThemeToggle />
      </header>

      <div className="mb-6">
        <PublicacionesFiltros
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
            parqueadero: filtros.parqueadero ?? undefined,
          }}
        />
      </div>

      <div className="mb-6">
        <PublicacionesDashboard
          publicaciones={publicaciones}
          hasActiveFilters={filtersActive}
          activeFilters={activeFilters}
        />
      </div>

      <PublicacionesManager
        publicaciones={publicaciones}
        fuentes={fuentes}
        hasActiveFilters={filtersActive}
      />
    </main>
  )
}
