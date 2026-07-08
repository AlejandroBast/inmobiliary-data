"use client"

import type React from "react"
import { useEffect, useState, useTransition } from "react"
import { useRouter } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  deletePublicacion,
  updateNotaPublicacion,
  validatePublicacionLinks,
  type PublicacionLinkStatus,
} from "@/app/actions/publicaciones"
import { PublicacionForm } from "@/components/publicacion-form"
import { formatCOP, formatDate, formatNumber } from "@/lib/format"
import type { Fuente } from "@/lib/db/schema"
import {
  AlertTriangle,
  Bath,
  BedDouble,
  Building2,
  CalendarClock,
  Car,
  CheckCircle2,
  ExternalLink,
  Eye,
  ImageIcon,
  Loader2,
  MapPin,
  MessageSquareText,
  Navigation,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react"
import { toast } from "sonner"

type Row = Record<string, any> & { id: number }
type ImageItem = { name: string; src: string }
type HtmlItem = { name: string; src: string }

function barrioLabel(value?: string | null) {
  return value?.trim() || "Sin barrio"
}

function phLabel(value?: string | null) {
  return value?.trim() || "Sin edificio/conjunto"
}

function shortNote(value?: string | null) {
  const clean = value?.trim()
  if (!clean) return "Sin nota"
  return clean.length > 72 ? `${clean.slice(0, 72)}...` : clean
}

function coordinatesText(publicacion: Row) {
  const coordenadas = String(publicacion.coordenadas ?? "").trim()
  if (coordenadas) return coordenadas

  const latitud = String(publicacion.latitud ?? "").trim()
  const longitud = String(publicacion.longitud ?? "").trim()

  return latitud && longitud ? `${latitud}, ${longitud}` : ""
}

function coordinatesMapUrl(publicacion: Row) {
  const latitud = String(publicacion.latitud ?? "").trim()
  const longitud = String(publicacion.longitud ?? "").trim()
  const coordenadas = coordinatesText(publicacion)

  if (latitud && longitud) {
    return `https://www.google.com/maps?q=${encodeURIComponent(`${latitud},${longitud}`)}`
  }

  return coordenadas ? `https://www.google.com/maps?q=${encodeURIComponent(coordenadas)}` : null
}

function rowLinks(publicacion: Row) {
  return {
    id: publicacion.id,
    linkOrigen: publicacion.linkOrigen ?? null,
    linksAdicionales: publicacion.linksAdicionales ?? null,
  }
}

export function PublicacionesManagerPro({
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
  const [detailHtmlFiles, setDetailHtmlFiles] = useState<HtmlItem[]>([])
  const [linkStatuses, setLinkStatuses] = useState<Record<number, PublicacionLinkStatus>>({})
  const [linksLoading, setLinksLoading] = useState(false)
  const [imagesLoading, setImagesLoading] = useState(false)
  const [htmlLoading, setHtmlLoading] = useState(false)
  const [notaDraft, setNotaDraft] = useState("")
  const [notaSaving, setNotaSaving] = useState(false)
  const [toDelete, setToDelete] = useState<Row | null>(null)
  const [isPending, startTransition] = useTransition()
  const router = useRouter()

  useEffect(() => {
    let active = true
    const items = publicaciones.map(rowLinks)

    if (items.length === 0) {
      setLinkStatuses({})
      setLinksLoading(false)
      return
    }

    setLinksLoading(true)

    validatePublicacionLinks(items)
      .then((results) => {
        if (!active) return
        setLinkStatuses(Object.fromEntries(results.map((result) => [result.id, result])))
      })
      .catch(() => {
        if (!active) return
        setLinkStatuses({})
      })
      .finally(() => {
        if (active) setLinksLoading(false)
      })

    return () => {
      active = false
    }
  }, [publicaciones])

  useEffect(() => {
    if (!detail) {
      setDetailImages([])
      setDetailHtmlFiles([])
      setImagesLoading(false)
      setHtmlLoading(false)
      setNotaDraft("")
      return
    }

    const currentDetail = detail
    const controller = new AbortController()
    setNotaDraft(currentDetail.notas ?? "")
    setImagesLoading(true)
    setHtmlLoading(true)

    async function loadEvidence() {
      try {
        const [imagesResponse, htmlResponse] = await Promise.all([
          fetch(`/api/publicaciones/${currentDetail.id}/imagenes`, { signal: controller.signal }),
          fetch(`/api/publicaciones/${currentDetail.id}/html`, { signal: controller.signal }),
        ])

        const imagesData = imagesResponse.ok ? ((await imagesResponse.json()) as { images?: ImageItem[] }) : { images: [] }
        const htmlData = htmlResponse.ok ? ((await htmlResponse.json()) as { html?: HtmlItem[] }) : { html: [] }

        setDetailImages(Array.isArray(imagesData.images) ? imagesData.images : [])
        setDetailHtmlFiles(Array.isArray(htmlData.html) ? htmlData.html : [])
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setDetailImages([])
          setDetailHtmlFiles([])
        }
      } finally {
        if (!controller.signal.aborted) {
          setImagesLoading(false)
          setHtmlLoading(false)
        }
      }
    }

    void loadEvidence()

    return () => controller.abort()
  }, [detail])

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
        toast.success("Publicacion eliminada.")
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

  function openHtmlFile() {
    const htmlFile = detailHtmlFiles[0]
    if (!htmlFile) return

    window.open(htmlFile.src, "_blank", "noopener,noreferrer")
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="rounded-lg border border-slate-200/70 bg-slate-50 px-4 py-3 dark:border-white/10 dark:bg-white/5">
          <p className="text-sm font-semibold">{publicaciones.length} publicaciones visibles</p>
          <p className="text-xs text-muted-foreground">
            {hasActiveFilters ? "Resultados filtrados desde el servidor." : "Inventario completo listo para analizar."}
          </p>
        </div>
        <Button onClick={openCreate} className="gap-2">
          <Plus className="size-4" />
          Nueva publicacion
        </Button>
      </div>

      {publicaciones.length === 0 ? (
        <Card className="border-slate-200/70 dark:border-white/10">
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted">
              <Building2 className="size-6 text-muted-foreground" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">
                {hasActiveFilters ? "No se encontraron publicaciones con los filtros seleccionados." : "Aun no hay publicaciones"}
              </p>
              <p className="text-sm text-muted-foreground">
                {hasActiveFilters ? "Prueba limpiando filtros o ajustando criterios." : "Crea tu primera publicacion inmobiliaria para comenzar."}
              </p>
            </div>
            {!hasActiveFilters && (
              <Button onClick={openCreate} className="gap-2">
                <Plus className="size-4" />
                Nueva publicacion
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card className="border-slate-200/70 bg-card/95 dark:border-white/10 dark:bg-zinc-950/70">
          <div className="flex flex-col gap-1 border-b bg-slate-50/60 px-4 py-3 dark:bg-white/[0.03] sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold tracking-tight">Resultados de publicaciones</h2>
              <p className="text-sm text-muted-foreground">Tabla compacta para comparar precio, ubicacion, fuente y caracteristicas.</p>
            </div>
            <Badge variant="outline" className="border-emerald-200 text-emerald-700 dark:border-emerald-400/30 dark:text-emerald-300">
              {publicaciones.length} registros
            </Badge>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-100/80 dark:bg-zinc-900">
                  <TableHead>ID</TableHead>
                  <TableHead>Publicacion</TableHead>
                  <TableHead>Ubicacion</TableHead>
                  <TableHead>Fuente</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="text-right">Area</TableHead>
                  <TableHead className="text-right">$/m2</TableHead>
                  <TableHead>Caracteristicas</TableHead>
                  <TableHead>Nota</TableHead>
                  <TableHead>Captura</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {publicaciones.map((p, index) => (
                  <TableRow
                    key={p.id}
                    className={[
                      "cursor-pointer transition-colors hover:bg-emerald-50/70 dark:hover:bg-emerald-400/10",
                      linkStatuses[p.id]?.ok === false
                        ? "border-red-300 bg-red-50/80 hover:bg-red-100/80 dark:border-red-400/40 dark:bg-red-950/35 dark:hover:bg-red-950/50"
                        : index % 2 === 0
                          ? "bg-background dark:bg-zinc-950/30"
                          : "bg-slate-50/45 dark:bg-white/[0.025]",
                    ].join(" ")}
                    onClick={() => setDetail(p)}
                  >
                    <TableCell className="font-medium">#{p.id}</TableCell>
                    <TableCell>
                      <div className="font-medium">{p.tipoInmueble || "Inmueble"}</div>
                      {p.codigoExterno && <div className="text-xs text-muted-foreground">{p.codigoExterno}</div>}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">{barrioLabel(p.barrio)}</div>
                      <div className="text-xs text-muted-foreground">
                        {p.ciudad || "Sin ubicacion"}
                      </div>
                      {coordinatesText(p) && (
                        <Badge variant="outline" className="mt-1 gap-1 border-emerald-200 bg-emerald-50 text-[11px] text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-300">
                          <MapPin className="size-3" />
                          GPS
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {p.fuenteNombre ? <Badge variant="secondary">{p.fuenteNombre}</Badge> : "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="font-semibold text-emerald-700 dark:text-emerald-200">{formatCOP(p.precio)}</div>
                      <div className="text-xs text-muted-foreground">{formatCOP(p.administracion)} admin.</div>
                    </TableCell>
                    <TableCell className="text-right">{formatNumber(p.m2, " m2")}</TableCell>
                    <TableCell className="text-right">{formatCOP(p.precioM2)}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant="outline" className="gap-1 border-slate-200 bg-white text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"><BedDouble className="size-3" />{p.habitaciones ?? "-"}</Badge>
                        <Badge variant="outline" className="gap-1 border-slate-200 bg-white text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"><Bath className="size-3" />{p.banios ?? "-"}</Badge>
                        <Badge variant="outline" className="gap-1 border-slate-200 bg-white text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"><Car className="size-3" />{p.parqueadero ?? "-"}</Badge>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-56 text-sm text-muted-foreground">{shortNote(p.notas)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <CalendarClock className="size-3.5" />
                        {formatDate(p.fechaCaptura)}
                      </div>
                    </TableCell>
                    <TableCell onClick={(event) => event.stopPropagation()}>
                      <div className="flex flex-wrap justify-end gap-1">
                        <Button variant="outline" size="sm" onClick={() => setDetail(p)} className="gap-1 border-emerald-200 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-400/30 dark:text-emerald-300 dark:hover:bg-emerald-400/10">
                          <Eye className="size-4" />
                          Ver publicacion
                        </Button>
                        <Button variant="ghost" size="icon-sm" onClick={() => setDetail(p)} aria-label="Nota">
                          <MessageSquareText className="size-4" />
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

      <Dialog open={!!detail} onOpenChange={(open) => !open && setDetail(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          {detail && (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-normal text-muted-foreground">#{detail.id}</span>
                  {detail.tipoInmueble || "Inmueble"}
                  {detail.fuenteNombre && <Badge variant="secondary">{detail.fuenteNombre}</Badge>}
                </DialogTitle>
                <DialogDescription>Capturado el {formatDate(detail.fechaCaptura)}</DialogDescription>
              </DialogHeader>

              <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <Detail label="Precio" value={formatCOP(detail.precio)} />
                <Detail label="Area" value={formatNumber(detail.m2, " m2")} />
                <Detail label="$/m2" value={formatCOP(detail.precioM2)} />
                <Detail label="Administracion" value={formatCOP(detail.administracion)} />
                <Detail label="Barrio" value={barrioLabel(detail.barrio)} />
                <Detail label="Ciudad" value={detail.ciudad || "-"} />
                <Detail label="Edificio / conjunto" value={phLabel(detail.ph)} />
                <Detail label="Habitaciones" value={detail.habitaciones ?? "-"} />
                <Detail label="Banos" value={detail.banios ?? "-"} />
                <Detail label="Parqueaderos" value={detail.parqueadero ?? "-"} />
                <Detail label="Estrato" value={detail.estrato ?? "-"} />
                <Detail label="Pisos" value={detail.pisos ?? "-"} />
                <Detail label="Antiguedad" value={detail.antiguedad || "-"} />
              </div>

              {detail.descripcion && (
                <TextBlock label="Descripcion" value={detail.descripcion} />
              )}

              <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50/70 p-4 dark:border-emerald-400/20 dark:bg-emerald-400/10">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-2">
                    <MapPin className="size-4 text-emerald-700 dark:text-emerald-300" />
                    <div>
                      <p className="text-sm font-medium">Coordenadas</p>
                      <p className="text-xs text-muted-foreground">{coordinatesText(detail) || "Sin coordenadas capturadas"}</p>
                    </div>
                  </div>
                  {coordinatesMapUrl(detail) && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0 gap-2"
                      onClick={() => {
                        const url = coordinatesMapUrl(detail)
                        if (url) window.open(url, "_blank", "noopener,noreferrer")
                      }}
                    >
                      <Navigation className="size-4" />
                      Abrir mapa
                    </Button>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
                  <Detail label="Latitud" value={detail.latitud || "-"} />
                  <Detail label="Longitud" value={detail.longitud || "-"} />
                  <Detail label="Direccion" value={detail.direccion || "-"} />
                </div>
              </div>

              <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-medium">Nota personalizada</p>
                    <p className="text-xs text-muted-foreground">Observaciones internas asociadas solo a esta publicacion.</p>
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
                <div className="flex items-center gap-2 text-sm font-medium">
                  <ImageIcon className="size-4" />
                  Imagenes
                </div>
                {imagesLoading ? (
                  <p className="text-sm text-muted-foreground">Cargando imagenes...</p>
                ) : detailImages.length ? (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {detailImages.map((image) => (
                      <a key={image.src} href={image.src} target="_blank" rel="noopener noreferrer" className="overflow-hidden rounded-lg border bg-muted">
                        <img src={image.src} alt={`Imagen de publicacion ${detail.id}`} className="h-28 w-full object-cover transition-transform hover:scale-105" />
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No hay imagenes guardadas para esta publicacion.</p>
                )}
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-medium text-muted-foreground">HTML capturado</p>
                  {detailHtmlFiles.length > 0 && (
                    <Button type="button" variant="outline" size="sm" onClick={openHtmlFile}>
                      Abrir HTML
                    </Button>
                  )}
                </div>
                {htmlLoading ? (
                  <p className="text-sm text-muted-foreground">Cargando HTML...</p>
                ) : detailHtmlFiles.length > 0 ? (
                  <div className="space-y-1 text-sm">
                    {detailHtmlFiles.map((file) => (
                      <a
                        key={file.src}
                        href={file.src}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block break-all text-primary hover:underline"
                      >
                        {file.name}
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No hay HTML guardado para esta publicacion.</p>
                )}
              </div>

              <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  <a href={detail.linkOrigen} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                    <ExternalLink className="size-4" />
                    Ver origen
                  </a>
                  {linksLoading && !linkStatuses[detail.id] && (
                    <Badge variant="outline" className="gap-1 border-slate-200 text-slate-600 dark:border-white/10 dark:text-slate-300">
                      <Loader2 className="size-3 animate-spin" />
                      Validando link
                    </Badge>
                  )}
                  {linkStatuses[detail.id]?.ok === true && (
                    <Badge variant="outline" className="gap-1 border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-300">
                      <CheckCircle2 className="size-3" />
                      Link disponible
                    </Badge>
                  )}
                  {linkStatuses[detail.id]?.ok === false && (
                    <Badge variant="outline" className="gap-1 border-red-300 bg-red-50 text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-200">
                      <AlertTriangle className="size-3" />
                      Link con problema
                    </Badge>
                  )}
                </div>
                <Button variant="outline" onClick={() => { const selected = detail; setDetail(null); openEdit(selected) }}>
                  Editar
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!toDelete} onOpenChange={(open) => !open && setToDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Eliminar publicacion</DialogTitle>
            <DialogDescription>
              Esta accion no se puede deshacer. Se eliminara la publicacion
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

function TextBlock({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="whitespace-pre-wrap text-sm">{value}</p>
    </div>
  )
}
