import { Card, CardContent } from "@/components/ui/card"
import { Building2, Download, Radar, Zap } from "lucide-react"
import Link from "next/link"
import type { LucideIcon } from "lucide-react"

const acciones: Array<{ icon: LucideIcon; label: string; detail: string; href: string; external?: boolean }> = [
  { icon: Building2, label: "Ver publicaciones", detail: "Explora y filtra el inventario", href: "/" },
  { icon: Radar, label: "Escanear fuentes", detail: "Actualiza el inventario", href: "/#escanear" },
  { icon: Download, label: "Exportar Excel", detail: "Descarga la base completa", href: "/api/export/database", external: true },
]

export function AccionesRapidas() {
  return (
    <Card className="surface-panel">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <span className="icon-chip tone-primary">
            <Zap className="size-4" />
          </span>
          <p className="text-sm font-medium">Acciones rapidas</p>
        </div>
        <div className="grid gap-2">
          {acciones.map((accion) => {
            const Icon = accion.icon
            const content = (
              <div className="group flex items-center gap-3 rounded-lg border border-border/70 bg-card px-3 py-2.5 transition-colors hover:border-primary/30 hover:bg-primary/5">
                <span className="icon-chip tone-slate shrink-0 transition-colors group-hover:border-primary/20 group-hover:bg-primary/10 group-hover:text-primary">
                  <Icon className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{accion.label}</p>
                  <p className="truncate text-xs text-muted-foreground">{accion.detail}</p>
                </div>
              </div>
            )
            return accion.external ? (
              <a key={accion.label} href={accion.href}>
                {content}
              </a>
            ) : (
              <Link key={accion.label} href={accion.href}>
                {content}
              </Link>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
