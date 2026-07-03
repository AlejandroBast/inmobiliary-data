import { getFuentes, getPublicaciones } from "@/app/actions/publicaciones"
import { PublicacionesManager } from "@/components/publicaciones-manager"
import { Building2 } from "lucide-react"

export const dynamic = "force-dynamic"

export default async function Page() {
  const [publicaciones, fuentes] = await Promise.all([getPublicaciones(), getFuentes()])

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

      <PublicacionesManager publicaciones={publicaciones} fuentes={fuentes} />
    </main>
  )
}
