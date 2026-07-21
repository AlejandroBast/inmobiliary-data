import { Card, CardContent } from "@/components/ui/card"
import { formatNumber } from "@/lib/format"
import { AlertTriangle, CheckCircle2 } from "lucide-react"
import type { LucideIcon } from "lucide-react"

type Alerta = {
  icon: LucideIcon
  label: string
  count: number
  href?: string
}

export function AlertasPanel({ alertas }: { alertas: Alerta[] }) {
  const activas = alertas.filter((alerta) => alerta.count > 0)

  return (
    <Card className="surface-panel">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <span className="icon-chip tone-amber">
            <AlertTriangle className="size-4" />
          </span>
          <p className="text-sm font-medium">Alertas importantes</p>
        </div>
        {activas.length ? (
          <ul className="space-y-2">
            {activas.map((alerta) => {
              const Icon = alerta.icon
              const content = (
                <div className="flex items-center gap-3 rounded-lg border border-amber-200/70 bg-amber-50 px-3 py-2.5 text-sm dark:border-amber-400/25 dark:bg-amber-400/10">
                  <Icon className="size-4 shrink-0 text-amber-700 dark:text-amber-300" />
                  <span className="min-w-0 flex-1 truncate text-amber-900 dark:text-amber-100">{alerta.label}</span>
                  <span className="shrink-0 font-semibold text-amber-800 dark:text-amber-200">
                    {formatNumber(alerta.count)}
                  </span>
                </div>
              )
              return (
                <li key={alerta.label}>
                  {alerta.href ? (
                    <a href={alerta.href} className="block transition-opacity hover:opacity-80">
                      {content}
                    </a>
                  ) : (
                    content
                  )}
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="flex items-center gap-3 rounded-lg border border-emerald-200/70 bg-emerald-50 px-3 py-3 text-sm text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200">
            <CheckCircle2 className="size-4 shrink-0" />
            Sin alertas activas: los datos visibles estan completos.
          </div>
        )}
      </CardContent>
    </Card>
  )
}
