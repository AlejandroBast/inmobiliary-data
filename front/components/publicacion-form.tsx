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
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { toast } from "sonner"
import { createPublicacion, updatePublicacion, type PublicacionInput } from "@/app/actions/publicaciones"
import type { Fuente } from "@/lib/db/schema"
import { NuevaFuenteDialog } from "./nueva-fuente-dialog"

type Row = Record<string, unknown> & { id: number }

export function PublicacionForm({
  fuentes,
  open,
  onOpenChange,
  editing,
}: {
  fuentes: Fuente[]
  open: boolean
  onOpenChange: (open: boolean) => void
  editing?: Row | null
}) {
  const [isPending, startTransition] = useTransition()
  const [fuenteList, setFuenteList] = useState<Fuente[]>(fuentes)
  const [fuenteId, setFuenteId] = useState<string>(editing ? String(editing.fuenteId) : "")

  const val = (key: string) => {
    const v = editing?.[key]
    return v === null || v === undefined ? "" : String(v)
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)

    if (!fuenteId) {
      toast.error("Selecciona una fuente inmobiliaria.")
      return
    }

    const num = (k: string) => {
      const v = fd.get(k)?.toString().trim()
      return v ? Number(v) : null
    }
    const str = (k: string) => {
      const v = fd.get(k)?.toString().trim()
      return v || null
    }
    const linksRaw = fd.get("linksAdicionales")?.toString().trim()

    const input: PublicacionInput = {
      fuenteId: Number(fuenteId),
      codigoExterno: str("codigoExterno"),
      linkOrigen: fd.get("linkOrigen")!.toString().trim(),
      linksAdicionales: linksRaw
        ? linksRaw.split("\n").map((l) => l.trim()).filter(Boolean)
        : null,
      coordenadas: str("coordenadas"),
      latitud: str("latitud"),
      longitud: str("longitud"),
      direccion: str("direccion"),
      ciudad: str("ciudad"),
      comuna: str("comuna"),
      barrio: str("barrio"),
      tipoInmueble: str("tipoInmueble"),
      ph: str("ph"),
      estrato: num("estrato"),
      descripcion: str("descripcion"),
      precio: Number(fd.get("precio")),
      m2: str("m2"),
      m2Construido: str("m2Construido"),
      antiguedad: str("antiguedad"),
      pisos: num("pisos"),
      habitaciones: num("habitaciones"),
      banios: num("banios"),
      parqueadero: num("parqueadero"),
      administracion: str("administracion"),
      notas: str("notas"),
    }

    if (!input.linkOrigen) {
      toast.error("El link de origen es obligatorio.")
      return
    }
    if (!input.precio || input.precio <= 0) {
      toast.error("El precio debe ser mayor a 0.")
      return
    }

    startTransition(async () => {
      const res = editing
        ? await updatePublicacion(editing.id, input)
        : await createPublicacion(input)
      if (res.success) {
        toast.success(editing ? "Publicación actualizada." : "Publicación creada.")
        onOpenChange(false)
      } else {
        toast.error(res.error)
      }
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{editing ? "Editar publicación" : "Nueva publicación"}</DialogTitle>
          <DialogDescription>
            Completa los datos del inmueble. Los campos marcados con * son obligatorios.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6" id="publicacion-form">
          {/* Origen */}
          <fieldset className="space-y-4">
            <legend className="text-sm font-medium text-muted-foreground">Origen</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Fuente inmobiliaria *</Label>
                <div className="flex gap-2">
                  <Select value={fuenteId} onValueChange={(v) => setFuenteId(v ?? "")}>
                    <SelectTrigger className="flex-1">
                      <SelectValue placeholder="Selecciona una fuente">
                        {(value: string) =>
                          fuenteList.find((f) => String(f.id) === value)?.nombre ?? "Selecciona una fuente"
                        }
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {fuenteList.map((f) => (
                        <SelectItem key={f.id} value={String(f.id)}>
                          {f.nombre}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <NuevaFuenteDialog
                    onCreated={(f) => {
                      setFuenteList((prev) =>
                        prev.some((p) => p.id === f.id) ? prev : [...prev, f],
                      )
                      setFuenteId(String(f.id))
                    }}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="codigoExterno">Código externo</Label>
                <Input id="codigoExterno" name="codigoExterno" defaultValue={val("codigoExterno")} />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="linkOrigen">Link de origen *</Label>
              <Input id="linkOrigen" name="linkOrigen" type="url" required defaultValue={val("linkOrigen")} placeholder="https://..." />
            </div>
            <div className="space-y-2">
              <Label htmlFor="linksAdicionales">Links adicionales (uno por línea)</Label>
              <Textarea
                id="linksAdicionales"
                name="linksAdicionales"
                rows={2}
                defaultValue={
                  Array.isArray(editing?.linksAdicionales)
                    ? (editing?.linksAdicionales as string[]).join("\n")
                    : ""
                }
              />
            </div>
          </fieldset>

          {/* Ubicación */}
          <fieldset className="space-y-4">
            <legend className="text-sm font-medium text-muted-foreground">Ubicación</legend>
            <div className="space-y-2">
              <Label htmlFor="direccion">Dirección</Label>
              <Input id="direccion" name="direccion" defaultValue={val("direccion")} />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="ciudad">Ciudad</Label>
                <Input id="ciudad" name="ciudad" defaultValue={editing ? val("ciudad") : "Pasto"} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="comuna">Comuna</Label>
                <Input id="comuna" name="comuna" defaultValue={val("comuna")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="barrio">Barrio</Label>
                <Input id="barrio" name="barrio" defaultValue={val("barrio")} />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="coordenadas">Coordenadas</Label>
                <Input id="coordenadas" name="coordenadas" defaultValue={val("coordenadas")} placeholder="1.2136, -77.2811" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="latitud">Latitud</Label>
                <Input id="latitud" name="latitud" type="number" step="any" defaultValue={val("latitud")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="longitud">Longitud</Label>
                <Input id="longitud" name="longitud" type="number" step="any" defaultValue={val("longitud")} />
              </div>
            </div>
          </fieldset>

          {/* Características */}
          <fieldset className="space-y-4">
            <legend className="text-sm font-medium text-muted-foreground">Características</legend>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="tipoInmueble">Tipo de inmueble</Label>
                <Input id="tipoInmueble" name="tipoInmueble" defaultValue={val("tipoInmueble")} placeholder="Apartamento, Casa..." />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ph">PH</Label>
                <Input id="ph" name="ph" defaultValue={val("ph")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="estrato">Estrato</Label>
                <Input id="estrato" name="estrato" type="number" min="0" defaultValue={val("estrato")} />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="antiguedad">Antigüedad</Label>
                <Input id="antiguedad" name="antiguedad" defaultValue={val("antiguedad")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pisos">Pisos</Label>
                <Input id="pisos" name="pisos" type="number" min="0" defaultValue={val("pisos")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="parqueadero">Parqueaderos</Label>
                <Input id="parqueadero" name="parqueadero" type="number" min="0" defaultValue={val("parqueadero")} />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="habitaciones">Habitaciones</Label>
                <Input id="habitaciones" name="habitaciones" type="number" min="0" defaultValue={val("habitaciones")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="banios">Baños</Label>
                <Input id="banios" name="banios" type="number" min="0" defaultValue={val("banios")} />
              </div>
            </div>
          </fieldset>

          {/* Precios y áreas */}
          <fieldset className="space-y-4">
            <legend className="text-sm font-medium text-muted-foreground">Precios y áreas</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="precio">Precio (COP) *</Label>
                <Input id="precio" name="precio" type="number" min="1" required defaultValue={val("precio")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="administracion">Administración (COP)</Label>
                <Input id="administracion" name="administracion" type="number" min="0" defaultValue={val("administracion")} />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="m2">Área (m²)</Label>
                <Input id="m2" name="m2" type="number" step="any" min="0" defaultValue={val("m2")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="m2Construido">Área construida (m²)</Label>
                <Input id="m2Construido" name="m2Construido" type="number" step="any" min="0" defaultValue={val("m2Construido")} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              El precio por m² se calcula automáticamente.
            </p>
          </fieldset>

          {/* Descripción */}
          <fieldset className="space-y-4">
            <legend className="text-sm font-medium text-muted-foreground">Descripción y notas</legend>
            <div className="space-y-2">
              <Label htmlFor="descripcion">Descripción</Label>
              <Textarea id="descripcion" name="descripcion" rows={3} defaultValue={val("descripcion")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="notas">Notas internas</Label>
              <Textarea id="notas" name="notas" rows={2} defaultValue={val("notas")} />
            </div>
          </fieldset>
        </form>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancelar
          </Button>
          <Button type="submit" form="publicacion-form" disabled={isPending}>
            {isPending ? "Guardando..." : editing ? "Guardar cambios" : "Crear publicación"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
