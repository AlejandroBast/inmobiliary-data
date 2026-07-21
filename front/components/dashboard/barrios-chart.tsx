"use client"

import { Card, CardContent } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { MapPinned } from "lucide-react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

const chartConfig = {
  count: {
    label: "Publicaciones",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig

export function BarriosChart({
  items,
}: {
  items: Array<{ label: string; count: number }>
}) {
  const top = [...items].reverse().slice(-7)

  return (
    <Card className="surface-panel">
      <CardContent className="space-y-4 p-4">
        <div className="flex items-center gap-2">
          <span className="icon-chip tone-slate">
            <MapPinned className="size-4" />
          </span>
          <p className="text-sm font-medium">Top barrios</p>
        </div>
        {top.length ? (
          <ChartContainer config={chartConfig} className="aspect-auto h-64 w-full">
            <BarChart data={top} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
              <CartesianGrid horizontal={false} strokeDasharray="3 3" />
              <XAxis type="number" hide />
              <YAxis
                dataKey="label"
                type="category"
                tickLine={false}
                axisLine={false}
                width={110}
                tick={{ fontSize: 12 }}
                tickFormatter={(value: string) => (value.length > 16 ? `${value.slice(0, 16)}…` : value)}
              />
              <ChartTooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltipContent hideLabel />} />
              <Bar dataKey="count" fill="var(--color-count)" radius={[0, 6, 6, 0]} barSize={16} />
            </BarChart>
          </ChartContainer>
        ) : (
          <p className="flex h-64 items-center justify-center text-sm text-muted-foreground">Sin datos visibles.</p>
        )}
      </CardContent>
    </Card>
  )
}
