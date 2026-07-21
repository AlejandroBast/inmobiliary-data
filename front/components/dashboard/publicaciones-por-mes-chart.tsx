"use client"

import { Card, CardContent } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { CalendarRange } from "lucide-react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"

const chartConfig = {
  count: {
    label: "Publicaciones",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig

export function PublicacionesPorMesChart({
  data,
}: {
  data: Array<{ month: string; count: number }>
}) {
  const hasData = data.some((item) => item.count > 0)

  return (
    <Card className="surface-panel">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <span className="icon-chip tone-primary">
            <CalendarRange className="size-4" />
          </span>
          <div>
            <p className="text-sm font-medium">Publicaciones por mes</p>
            <p className="text-xs text-muted-foreground">Basado en la fecha de captura del scraper.</p>
          </div>
        </div>
        {hasData ? (
          <ChartContainer config={chartConfig} className="aspect-auto h-56 w-full">
            <AreaChart data={data} margin={{ left: -20, right: 12, top: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="fillCount" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-count)" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="var(--color-count)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="month" tickLine={false} axisLine={false} tickMargin={8} minTickGap={24} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="line" />} />
              <Area
                dataKey="count"
                type="monotone"
                fill="url(#fillCount)"
                stroke="var(--color-count)"
                strokeWidth={2}
              />
            </AreaChart>
          </ChartContainer>
        ) : (
          <p className="flex h-56 items-center justify-center text-sm text-muted-foreground">
            Sin datos suficientes para graficar por mes.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
