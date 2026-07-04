"use client"

import type React from "react"

import { useState, useTransition } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Plus } from "lucide-react"
import { toast } from "sonner"
import { createFuente } from "@/app/actions/publicaciones"
import type { Fuente } from "@/lib/db/schema"

export function NuevaFuenteDialog({ onCreated }: { onCreated?: (fuente: Fuente) => void }) {
  const [open, setOpen] = useState(false)
  const [isPending, startTransition] = useTransition()

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const nombre = fd.get("nombre")?.toString().trim()
    if (!nombre) {
      toast.error("El nombre de la fuente es obligatorio.")
      return
    }
    startTransition(async () => {
      const res = await createFuente({
        nombre,
        tipoFuente: fd.get("tipoFuente")?.toString().trim() || null,
        urlBase: fd.get("urlBase")?.toString().trim() || null,
      })
      if (res.success && res.fuente) {
        toast.success("Fuente creada.")
        onCreated?.(res.fuente)
        setOpen(false)
      } else {
        toast.error(res.error ?? "No se pudo crear la fuente.")
      }
    })
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button type="button" variant="outline" size="icon" aria-label="Nueva fuente" />
        }
      >
        <Plus className="size-4" />
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nueva fuente inmobiliaria</DialogTitle>
          <DialogDescription>Agrega una fuente para clasificar tus publicaciones.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4" id="fuente-form">
          <div className="space-y-2">
            <Label htmlFor="fuente-nombre">Nombre *</Label>
            <Input id="fuente-nombre" name="nombre" required placeholder="Fincaraíz, Metrocuadrado..." />
          </div>
          <div className="space-y-2">
            <Label htmlFor="fuente-tipo">Tipo de fuente</Label>
            <Input id="fuente-tipo" name="tipoFuente" placeholder="Portal, Inmobiliaria, Particular..." />
          </div>
          <div className="space-y-2">
            <Label htmlFor="fuente-url">URL base</Label>
            <Input id="fuente-url" name="urlBase" type="url" placeholder="https://..." />
          </div>
        </form>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={isPending}>
            Cancelar
          </Button>
          <Button type="submit" form="fuente-form" disabled={isPending}>
            {isPending ? "Guardando..." : "Crear fuente"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
