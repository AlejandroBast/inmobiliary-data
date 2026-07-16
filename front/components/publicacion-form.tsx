"use client"

import type React from "react"

import { useEffect, useState, useTransition } from "react"
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
import { ImageIcon, Loader2, X } from "lucide-react"

type Row = Record<string, unknown> & { id: number }
type ImageItem = { name: string; src: string }

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
  const [images, setImages] = useState<ImageItem[]>([])
  const [imagesLoading, setImagesLoading] = useState(false)
  const [deletingImage, setDeletingImage] = useState<string | null>(null)

  useEffect(() => {
    setFuenteId(editing ? String(editing.fuenteId) : "")
  }, [editing])

  useEffect(() => {
    if (!open || !editing) {
      setImages([])
      setImagesLoading(false)
      setDeletingImage(null)
      return
    }

    const controller = new AbortController()
    setImagesLoading(true)
    fetch(`/api/publicaciones/${editing.id}/imagenes`, { signal: controller.signal })
      .then(async (response) => response.ok ? response.json() as Promise<{ images?: ImageItem[] }> : { images: [] })
      .then((data) => setImages(Array.isArray(data.images) ? data.images : []))
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setImages([])
      })
      .finally(() => {
        if (!controller.signal.aborted) setImagesLoading(false)
      })

    return () => controller.abort()
  }, [editing, open])

  async function deleteImage(image: ImageItem) {
    if (!editing || deletingImage) return
    if (!window.confirm(`¿Estás seguro de que deseas eliminar esta imagen?\n\n${image.name}\n\nEsta acción no se puede deshacer.`)) return

    setDeletingImage(image.name)
    try {
      const response = await fetch(`/api/publicaciones/${editing.id}/imagenes/${encodeURIComponent(image.name)}`, { method: "DELETE" })
      const result = await response.json() as { success?: boolean; error?: string }
      if (!response.ok || !result.success) {
        toast.error(result.error || "No se pudo eliminar la imagen.")
        return
      }
      setImages((current) => current.filter((item) => item.name !== image.name))
      toast.success("Imagen eliminada.")
    } catch {
      toast.error("No se pudo eliminar la imagen.")
    } finally {
      setDeletingImage(null)
    }
  }

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
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="ciudad">Ciudad</Label>
                <Input id="ciudad" name="ciudad" defaultValue={editing ? val("ciudad") : "Pasto"} />
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

          {editing && (
            <fieldset className="space-y-3">
              <div>
                <legend className="text-sm font-medium text-muted-foreground">Imagenes guardadas</legend>
                <p className="text-xs text-muted-foreground">Elimina las capturas que no correspondan a esta publicacion.</p>
              </div>
              {imagesLoading ? (
                <div className="flex items-center gap-2 rounded-lg border p-4 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> Cargando imagenes...
                </div>
              ) : images.length === 0 ? (
                <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                  <ImageIcon className="size-4" /> Esta publicacion no tiene imagenes guardadas.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {images.map((image) => (
                    <div key={image.name} className="group relative overflow-hidden rounded-lg border bg-muted">
                      <img src={image.src} alt={image.name} className="aspect-[4/3] w-full object-cover transition group-hover:brightness-75" loading="lazy" />
                      <Button
                        type="button"
                        variant="destructive"
                        size="icon"
                        className="absolute right-2 top-2 size-9 rounded-full border-2 border-white bg-red-600 text-white opacity-0 shadow-lg transition hover:bg-red-700 group-hover:opacity-100 focus-visible:opacity-100"
                        aria-label={`Eliminar ${image.name}`}
                        title="Eliminar imagen"
                        disabled={deletingImage !== null}
                        onClick={() => void deleteImage(image)}
                      >
                        {deletingImage === image.name ? <Loader2 className="size-5 animate-spin" /> : <X className="size-5 stroke-[3]" />}
                      </Button>
                      <div className="absolute inset-x-0 bottom-0 truncate bg-black/65 px-2 py-1.5 text-xs text-white opacity-0 transition group-hover:opacity-100" title={image.name}>
                        {image.name}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </fieldset>
          )}
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
