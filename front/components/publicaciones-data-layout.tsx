"use client"

import type { ReactNode } from "react"
import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Filter, X } from "lucide-react"

export function PublicacionesDataLayout({
  activeFilterCount,
  filterPanel,
  children,
}: {
  activeFilterCount: number
  filterPanel: ReactNode
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative min-w-0">
      <div id="filtros" className="relative z-50 mb-4 flex items-center justify-between gap-3">
        <Button
          type="button"
          variant={open ? "default" : "outline"}
          size="icon-lg"
          aria-label={open ? "Cerrar filtros" : "Abrir filtros"}
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
          className={["relative", open ? "" : "text-primary hover:bg-primary/10"].join(" ")}
        >
          <Filter className="size-4" />
          {activeFilterCount > 0 && (
            <span className="absolute -right-1 -top-1 flex min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-5 text-primary-foreground ring-2 ring-background">
              {activeFilterCount}
            </span>
          )}
        </Button>

        {activeFilterCount > 0 && (
          <Badge variant="outline" className="tone-primary">
            {activeFilterCount} filtros activos
          </Badge>
        )}
      </div>

      {children}

      {open && (
        <div className="fixed inset-0 z-40">
          <button
            type="button"
            aria-label="Cerrar filtros"
            className="animate-fade-in absolute inset-0 bg-black/45 backdrop-blur-[1px]"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute right-0 top-0 flex h-full w-full max-w-[430px] flex-col border-l border-border/70 bg-background shadow-2xl duration-200 animate-in slide-in-from-right">
            <div className="flex items-center justify-between gap-3 border-b border-border/70 bg-muted/30 px-4 py-3 pl-16 sm:pl-4">
              <div>
                <p className="text-sm font-semibold">Filtros de busqueda</p>
                <p className="text-xs text-muted-foreground">Abre y cierra este panel sin perder espacio en la tabla.</p>
              </div>
              <Button type="button" variant="ghost" size="icon" aria-label="Cerrar filtros" onClick={() => setOpen(false)}>
                <X className="size-4" />
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {filterPanel}
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
