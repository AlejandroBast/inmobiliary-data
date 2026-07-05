import {
  getBarrios,
  getFuentes,
  getPublicaciones,
  getPublicacionesTotal,
  type PublicacionFilters,
} from "@/app/actions/publicaciones"
import { PublicacionesManager } from "@/components/publicaciones-manager"
import { PublicacionesFiltros } from "@/components/publicaciones-filtros"
import { PublicacionesStats } from "@/components/publicaciones-stats"
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

  const [publicaciones, fuentes, barriosData, totalPublicaciones] = await Promise.all([
    getPublicaciones(filtros),
    getFuentes(),
    getBarrios(),
    getPublicacionesTotal(),
  ])

  const filtrosActivos = hasActiveFilters(filtros)

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8 flex items-center gap-3">
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
        <PublicacionesStats
          publicaciones={publicaciones}
          totalPublicaciones={totalPublicaciones}
          hasActiveFilters={filtrosActivos}
        />
      </div>

      <PublicacionesManager
        publicaciones={publicaciones}
        fuentes={fuentes}
        hasActiveFilters={filtrosActivos}
      />
    </main>
  )
}
