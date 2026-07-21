import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { formatCOP, formatDate } from "@/lib/format"
import { Clock } from "lucide-react"

type ActividadRow = Record<string, unknown> & {
  id: number
  tipoInmueble?: string | null
  barrio?: string | null
  precio?: unknown
  fuenteNombre?: string | null
  fechaCaptura?: unknown
}

export function ActividadReciente({ items }: { items: ActividadRow[] }) {
  const recent = items.slice(0, 6)

  return (
    <Card className="surface-panel">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <span className="icon-chip tone-slate">
            <Clock className="size-4" />
          </span>
          <p className="text-sm font-medium">Actividad reciente</p>
        </div>
        {recent.length ? (
          <ul className="divide-y divide-border/60">
            {recent.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 py-2.5 text-sm first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate font-medium">
                    #{item.id} · {item.tipoInmueble || "Inmueble"}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {item.barrio || "Sin barrio"} {item.fuenteNombre ? `· ${item.fuenteNombre}` : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-medium text-primary">{formatCOP(item.precio as never)}</p>
                  <p className="text-xs text-muted-foreground">{formatDate(item.fechaCaptura as never)}</p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-4 text-center text-sm text-muted-foreground">Sin actividad reciente.</p>
        )}
        <div className="pt-1">
          <Badge variant="outline" className="tone-slate">Ordenado por fecha de captura</Badge>
        </div>
      </CardContent>
    </Card>
  )
}
