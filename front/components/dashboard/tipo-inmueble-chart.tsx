"use client"

import { Card, CardContent } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { formatNumber } from "@/lib/format"
import { Home } from "lucide-react"
import { Cell, Pie, PieChart } from "recharts"

const PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
]

export function TipoInmuebleChart({
  items,
}: {
  items: Array<{ label: string; count: number }>
}) {
  const top = items.slice(0, 5)
  const total = items.reduce((sum, item) => sum + item.count, 0)

  const chartConfig = Object.fromEntries(
    top.map((item, index) => [item.label, { label: item.label, color: PALETTE[index % PALETTE.length] }]),
  ) satisfies ChartConfig

  return (
    <Card className="surface-panel">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <span className="icon-chip tone-primary">
            <Home className="size-4" />
          </span>
          <div>
            <p className="text-sm font-medium">Distribucion por tipo de inmueble</p>
            <p className="text-xs text-muted-foreground">Top 5 categorias visibles.</p>
          </div>
        </div>
        {top.length ? (
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <ChartContainer config={chartConfig} className="aspect-square h-44 w-44 shrink-0">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent hideLabel nameKey="label" />} />
                <Pie data={top} dataKey="count" nameKey="label" innerRadius={44} outerRadius={70} strokeWidth={4}>
                  {top.map((item, index) => (
                    <Cell key={item.label} fill={PALETTE[index % PALETTE.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
            <div className="w-full min-w-0 space-y-2">
              {top.map((item, index) => (
                <div key={item.label} className="flex items-center gap-2 text-sm">
                  <span
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: PALETTE[index % PALETTE.length] }}
                  />
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  <span className="shrink-0 font-medium tabular-nums">{formatNumber(item.count)}</span>
                  <span className="w-10 shrink-0 text-right text-xs text-muted-foreground">
                    {total > 0 ? Math.round((item.count / total) * 100) : 0}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="flex h-44 items-center justify-center text-sm text-muted-foreground">Sin datos visibles.</p>
        )}
      </CardContent>
    </Card>
  )
}
