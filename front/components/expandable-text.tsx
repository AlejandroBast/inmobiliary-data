"use client"

import { cn } from "@/lib/utils"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

/**
 * Texto de una sola linea truncado por CSS a `maxWidth`, con el valor
 * completo disponible en un tooltip cuando no entra. Pensado para celdas de
 * tabla con contenido de longitud variable (PH, Barrio, Notas, Descripcion...)
 * donde el texto no debe poder expandir la columna que lo contiene.
 */
export function ExpandableText({
  text,
  maxWidth = 200,
  truncateLength = 40,
  emptyFallback = "-",
  className,
}: {
  text?: string | null
  maxWidth?: number
  truncateLength?: number
  emptyFallback?: string
  className?: string
}) {
  const value = text?.trim()

  if (!value) {
    return <span className={cn("text-muted-foreground", className)}>{emptyFallback}</span>
  }

  const span = (
    <span className={cn("block truncate", className)} style={{ maxWidth }}>
      {value}
    </span>
  )

  if (value.length <= truncateLength) {
    return span
  }

  return (
    <Tooltip>
      <TooltipTrigger render={span} />
      <TooltipContent>{value}</TooltipContent>
    </Tooltip>
  )
}
