"use client"

import type React from "react"
import { useEffect, useState, useTransition } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Card, CardContent } from "@/components/ui/card"
import { Plus, Pencil, Trash2, ExternalLink, Building2, ChevronLeft, ChevronRight, X, MessageSquareText } from "lucide-react"
import { toast } from "sonner"
import { PublicacionForm } from "./publicacion-form"
import { deletePublicacion, updateNotaPublicacion } from "@/app/actions/publicaciones"
import { formatCOP, formatNumber, formatDate } from "@/lib/format"
import type { Fuente } from "@/lib/db/schema"
import { Textarea } from "@/components/ui/textarea"

type Row = Record<string, any> & { id: number }
type ImageItem = { name: string; src: string }

export function PublicacionesManager({
  publicaciones,
  fuentes,
  hasActiveFilters,
}: {
  publicaciones: Row[]
  fuentes: Fuente[]
  hasActiveFilters: boolean
}) {
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Row | null>(null)
  const [detail, setDetail] = useState<Row | null>(null)
  const [detailImages, setDetailImages] = useState<ImageItem[]>([])
  const [imagesLoading, setImagesLoading] = useState(false)
  const [viewerIndex, setViewerIndex] = useState<number | null>(null)
  const [notaDraft, setNotaDraft] = useState("")
  const [notaSaving, setNotaSaving] = useState(false)
  const [toDelete, setToDelete] = useState<Row | null>(null)
  const [isPending, startTransition] = useTransition()
  const router = useRouter()

  useEffect(() => {
    if (!detail) {
      setDetailImages([])
      setImagesLoading(false)
      setViewerIndex(null)
      setNotaDraft("")
      return
    }

    const currentDetail = detail
    setNotaDraft(currentDetail.notas ?? "")

    const controller = new AbortController()

    async function loadImages() {
      setImagesLoading(true)
      try {
        const response = await fetch(`/api/publicaciones/${currentDetail.id}/imagenes`, {
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error("No se pudieron cargar las imágenes.")
        }

        const data = (await response.json()) as { images?: ImageItem[] }
        setDetailImages(Array.isArray(data.images) ? data.images : [])
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return
        }
        setDetailImages([])
      } finally {
        if (!controller.signal.aborted) {
          setImagesLoading(false)
        }
      }
    }

    void loadImages()

    return () => controller.abort()
  }, [detail])

  const viewerImage = viewerIndex !== null ? detailImages[viewerIndex] : null
  const currentViewerIndex = viewerIndex ?? 0

  function openViewer(index: number) {
    setViewerIndex(index)
  }

  function closeViewer() {
    setViewerIndex(null)
  }

  function goToPreviousImage() {
    if (viewerIndex === null || detailImages.length === 0) return
    setViewerIndex((viewerIndex - 1 + detailImages.length) % detailImages.length)
  }

  function goToNextImage() {
    if (viewerIndex === null || detailImages.length === 0) return
    setViewerIndex((viewerIndex + 1) % detailImages.length)
  }

  function openCreate() {
    setEditing(null)
    setFormOpen(true)
  }

  function openEdit(row: Row) {
    setEditing(row)
    setFormOpen(true)
  }

  function confirmDelete() {
    if (!toDelete) return
    startTransition(async () => {
      const res = await deletePublicacion(toDelete.id)
      if (res.success) {
        toast.success("Publicación eliminada.")
        setToDelete(null)
      } else {
        toast.error(res.error)
      }
    })
  }

  async function saveNota() {
    if (!detail) return

    setNotaSaving(true)
    try {
      const res = await updateNotaPublicacion(detail.id, notaDraft)
      if (res.success) {
        toast.success("Nota guardada.")
        setDetail((current) => (current ? { ...current, notas: notaDraft.trim() || null } : current))
        router.refresh()
      } else {
        toast.error(res.error)
      }
    } finally {
      setNotaSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="rounded-lg border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          {hasActiveFilters
            ? "Mostrando publicaciones filtradas desde el servidor."
            : "Mostrando todas las publicaciones registradas."}
        </div>
        <Button onClick={openCreate} className="gap-2">
          <Plus className="size-4" />
          Nueva publicación
        </Button>
      </div>

      {publicaciones.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted">
              <Building2 className="size-6 text-muted-foreground" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">
                {hasActiveFilters ? "No se encontraron publicaciones con los filtros seleccionados." : "Aún no hay publicaciones"}
              </p>
              <p className="text-sm text-muted-foreground">
                {hasActiveFilters
                  ? "Prueba limpiando los filtros o ajustando uno de los criterios de búsqueda."
                  : publicaciones.length === 0
                  ? "Crea tu primera publicación inmobiliaria para comenzar."
                  : "Prueba con otros términos de búsqueda."}
              </p>
            </div>
            {!hasActiveFilters && publicaciones.length === 0 && (
              <Button onClick={openCreate} className="gap-2">
                <Plus className="size-4" />
                Nueva publicación
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Inmueble</TableHead>
                  <TableHead>Ubicación</TableHead>
                  <TableHead>Coordenadas</TableHead>
                  <TableHead>Fuente</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="text-right">Área</TableHead>
                  <TableHead className="text-right">$/m²</TableHead>
                  <TableHead className="text-center">Hab.</TableHead>
                  <TableHead className="text-center">Baños</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {publicaciones.map((p) => (
                  <TableRow
                    key={p.id}
                    className="cursor-pointer"
                    onClick={() => setDetail(p)}
                  >
                    <TableCell className="font-medium">#{p.id}</TableCell>
                    <TableCell>
                      <div className="font-medium">{p.tipoInmueble || "Inmueble"}</div>
                      {p.codigoExterno && (
                        <div className="text-xs text-muted-foreground">{p.codigoExterno}</div>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">{p.barrio || p.direccion || "—"}</div>
                      <div className="text-xs text-muted-foreground">{p.ciudad || "—"}</div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {p.coordenadas || (p.latitud && p.longitud ? `${p.latitud}, ${p.longitud}` : "—")}
                    </TableCell>
                    <TableCell>
                      {p.fuenteNombre ? (
                        <Badge variant="secondary">{p.fuenteNombre}</Badge>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell className="text-right font-medium">{formatCOP(p.precio)}</TableCell>
                    <TableCell className="text-right">{formatNumber(p.m2, " m²")}</TableCell>
                    <TableCell className="text-right">{formatCOP(p.precioM2)}</TableCell>
                    <TableCell className="text-center">{p.habitaciones ?? "—"}</TableCell>
                    <TableCell className="text-center">{p.banios ?? "—"}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex flex-wrap justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDetail(p)}
                          className="gap-1"
                        >
                          <MessageSquareText className="size-4" />
                          {p.notas ? "Editar nota" : "Agregar nota"}
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => openEdit(p)} aria-label="Editar">
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setToDelete(p)}
                          aria-label="Eliminar"
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      {formOpen && (
        <PublicacionForm
          key={editing ? `edit-${editing.id}` : "create"}
          fuentes={fuentes}
          open={formOpen}
          onOpenChange={setFormOpen}
          editing={editing}
        />
      )}

      {/* Detalle */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          {detail && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <span className="text-sm font-normal text-muted-foreground">#{detail.id}</span>
                  {detail.tipoInmueble || "Inmueble"}
                  {detail.fuenteNombre && <Badge variant="secondary">{detail.fuenteNombre}</Badge>}
                </DialogTitle>
                <DialogDescription>
                  Capturado el {formatDate(detail.fechaCaptura)}
                </DialogDescription>
              </DialogHeader>
              <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                <Detail label="ID" value={`#${detail.id}`} />
                <Detail label="Precio" value={formatCOP(detail.precio)} />
                <Detail label="Administración" value={formatCOP(detail.administracion)} />
                <Detail label="Área" value={formatNumber(detail.m2, " m²")} />
                <Detail label="$/m²" value={formatCOP(detail.precioM2)} />
                <Detail label="Área construida" value={formatNumber(detail.m2Construido, " m²")} />
                <Detail label="$/m² construido" value={formatCOP(detail.precioM2Construido)} />
                <Detail label="Coordenadas" value={detail.coordenadas || (detail.latitud && detail.longitud ? `${detail.latitud}, ${detail.longitud}` : "—")} />
                <Detail label="Habitaciones" value={detail.habitaciones ?? "—"} />
                <Detail label="Baños" value={detail.banios ?? "—"} />
                <Detail label="Parqueaderos" value={detail.parqueadero ?? "—"} />
                <Detail label="Estrato" value={detail.estrato ?? "—"} />
                <Detail label="Pisos" value={detail.pisos ?? "—"} />
                <Detail label="Antigüedad" value={detail.antiguedad || "—"} />
                <Detail label="Ciudad" value={detail.ciudad || "—"} />
                <Detail label="Comuna" value={detail.comuna || "—"} />
                <Detail label="Barrio" value={detail.barrio || "—"} />
                <Detail label="PH" value={detail.ph || "—"} />
              </div>
              {detail.direccion && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Dirección</p>
                  <p className="text-sm">{detail.direccion}</p>
                </div>
              )}
              {detail.descripcion && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Descripción</p>
                  <p className="text-sm whitespace-pre-wrap">{detail.descripcion}</p>
                </div>
              )}
              {detail.notas && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Notas</p>
                  <p className="text-sm whitespace-pre-wrap">{detail.notas}</p>
                </div>
              )}
              <div className="space-y-3 rounded-lg border bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">Nota personalizada</p>
                    <p className="text-xs text-muted-foreground">
                      Agrega observaciones internas para esta publicación.
                    </p>
                  </div>
                  <Button type="button" onClick={saveNota} disabled={notaSaving} className="shrink-0">
                    {notaSaving ? "Guardando..." : "Guardar nota"}
                  </Button>
                </div>
                <Textarea
                  value={notaDraft}
                  onChange={(event) => setNotaDraft(event.target.value)}
                  placeholder="Escribe una nota interna..."
                  rows={4}
                />
              </div>
              <div className="space-y-3">
                <p className="text-xs font-medium text-muted-foreground">Imágenes</p>
                {imagesLoading ? (
                  <p className="text-sm text-muted-foreground">Cargando imágenes...</p>
                ) : detailImages.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {detailImages.map((image, index) => (
                      <button
                        type="button"
                        key={image.src}
                        onClick={() => openViewer(index)}
                        className="group overflow-hidden rounded-lg border bg-muted text-left"
                      >
                        <img
                          src={image.src}
                          alt={`Imagen de la publicación ${detail.id}`}
                          className="h-32 w-full object-cover transition-transform group-hover:scale-105"
                        />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No hay imágenes guardadas para esta publicación.</p>
                )}
              </div>
              <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
                <a
                  href={detail.linkOrigen}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                >
                  <ExternalLink className="size-4" />
                  Ver origen
                </a>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => { const d = detail; setDetail(null); openEdit(d) }}>
                    Editar
                  </Button>
                </div>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={viewerIndex !== null} onOpenChange={(open) => !open && closeViewer()}>
        <DialogContent className="max-h-[95vh] max-w-5xl overflow-hidden p-0">
          {viewerImage && detail && (
            <div className="relative flex min-h-[70vh] flex-col bg-black text-white">
              <div className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between p-3">
                <div className="rounded-full bg-black/60 px-3 py-1 text-xs text-white/80 backdrop-blur">
                  {currentViewerIndex + 1} / {detailImages.length}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={closeViewer}
                  className="rounded-full bg-black/60 text-white hover:bg-black/80 hover:text-white"
                  aria-label="Cerrar visor"
                >
                  <X className="size-5" />
                </Button>
              </div>

              <div className="flex flex-1 items-center justify-center px-14 py-14">
                <img
                  src={viewerImage.src}
                  alt={`Imagen ${currentViewerIndex + 1} de la publicación ${detail.id}`}
                  className="max-h-[75vh] max-w-full rounded-xl object-contain shadow-2xl"
                />
              </div>

              <div className="absolute inset-y-0 left-0 flex items-center p-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={goToPreviousImage}
                  className="rounded-full bg-black/60 text-white hover:bg-black/80 hover:text-white"
                  aria-label="Imagen anterior"
                >
                  <ChevronLeft className="size-6" />
                </Button>
              </div>

              <div className="absolute inset-y-0 right-0 flex items-center p-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={goToNextImage}
                  className="rounded-full bg-black/60 text-white hover:bg-black/80 hover:text-white"
                  aria-label="Imagen siguiente"
                >
                  <ChevronRight className="size-6" />
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Confirmar borrado */}
      <Dialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Eliminar publicación</DialogTitle>
            <DialogDescription>
              Esta acción no se puede deshacer. Se eliminará la publicación
              {toDelete?.barrio ? ` de ${toDelete.barrio}` : ""} de forma permanente.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)} disabled={isPending}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={isPending}>
              {isPending ? "Eliminando..." : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  )
}
