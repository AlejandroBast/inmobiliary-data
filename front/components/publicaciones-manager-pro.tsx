"use client"

import type React from "react"
import { useEffect, useRef, useState, useTransition } from "react"
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
  descartarCoincidenciaPublicaciones,
  getComparacionPublicaciones,
  updateNotaPublicacion,
  validatePublicacionLinks,
  type ComparacionPublicacion,
  type CoincidenciaPublicacion,
  type PublicacionLinkStatus,
} from "@/app/actions/publicaciones"
import { ExpandableText } from "@/components/expandable-text"
import { PublicacionForm } from "@/components/publicacion-form"
import { PublicacionesColumnFilters } from "@/components/publicaciones-column-filters"
import { formatCOP, formatDate, formatNumber } from "@/lib/format"
import type { Fuente } from "@/lib/db/schema"
import {
  AlertTriangle,
  Bath,
  BedDouble,
  Building2,
  CalendarClock,
  Car,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  CircleX,
  Columns3,
  ExternalLink,
  Eye,
  HelpCircle,
  ImageIcon,
  Loader2,
  MapPin,
  MessageSquareText,
  Navigation,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react"
import { toast } from "sonner"

type Row = Record<string, any> & { id: number; coincidencias?: CoincidenciaPublicacion[] }
type ImageItem = { name: string; src: string }
type HtmlItem = { name: string; src: string }
type ComparisonDismissTarget = {
  coincidenciaId: number
  rootId: number
  relatedId: number
}

function thumbSrc(src: string, width: number) {
  return `${src}?w=${width}`
}

const CAROUSEL_THUMB_WIDTH = 640
const DETAIL_THUMB_WIDTH = 320

function ComparisonImageCarousel({
  publicationId,
  images,
  children,
}: {
  publicationId: number
  images: ImageItem[]
  children?: React.ReactNode
}) {
  const [imageIndex, setImageIndex] = useState(0)
  const preloadedImages = useRef<Map<string, HTMLImageElement>>(new Map())
  const imageCount = images.length
  const safeImageIndex = imageCount > 0 ? imageIndex % imageCount : 0
  const image = images[safeImageIndex]

  useEffect(() => {
    setImageIndex(0)
    preloadedImages.current.clear()
  }, [publicationId, images])

  useEffect(() => {
    if (imageCount <= 1) return

    const neighborIndexes = [
      (safeImageIndex - 1 + imageCount) % imageCount,
      (safeImageIndex + 1) % imageCount,
    ]

    for (const neighborIndex of neighborIndexes) {
      const rawSource = images[neighborIndex]?.src
      if (!rawSource) continue
      const source = thumbSrc(rawSource, CAROUSEL_THUMB_WIDTH)
      if (preloadedImages.current.has(source)) continue

      const preload = new window.Image()
      preload.decoding = "async"
      preload.src = source
      preloadedImages.current.set(source, preload)
      void preload.decode().catch(() => undefined)
    }
  }, [imageCount, images, safeImageIndex])

  function moveImage(direction: -1 | 1) {
    setImageIndex((currentIndex) => {
      if (imageCount <= 1) return 0
      const normalizedIndex = ((currentIndex % imageCount) + imageCount) % imageCount
      return (normalizedIndex + direction + imageCount) % imageCount
    })
  }

  return (
    <div className="relative aspect-[16/10] overflow-hidden bg-slate-100 dark:bg-white/5">
      {image ? (
        <img
          src={thumbSrc(image.src, CAROUSEL_THUMB_WIDTH)}
          alt={`Publicacion ${publicationId}`}
          className="size-full select-none object-cover"
          decoding="async"
          loading="eager"
          fetchPriority="high"
          draggable={false}
        />
      ) : (
        <div className="flex size-full flex-col items-center justify-center gap-2 text-muted-foreground">
          <ImageIcon className="size-8" />
          <span className="text-xs">Sin imagen disponible</span>
        </div>
      )}

      {children}

      {imageCount > 1 && (
        <>
          <Button
            type="button"
            variant="secondary"
            size="icon"
            aria-label={`Foto anterior de la publicacion ${publicationId}`}
            className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full border border-white/30 bg-black/55 text-white shadow-lg backdrop-blur hover:bg-black/75 hover:text-white"
            onClick={() => moveImage(-1)}
          >
            <ChevronLeft className="size-5" />
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="icon"
            aria-label={`Foto siguiente de la publicacion ${publicationId}`}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full border border-white/30 bg-black/55 text-white shadow-lg backdrop-blur hover:bg-black/75 hover:text-white"
            onClick={() => moveImage(1)}
          >
            <ChevronRight className="size-5" />
          </Button>
          <span className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/65 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur">
            {safeImageIndex + 1} / {imageCount}
          </span>
        </>
      )}
    </div>
  )
}

function barrioLabel(value?: string | null) {
  return value?.trim() || "Sin barrio"
}

function phLabel(value?: string | null) {
  const trimmed = value?.trim()
  if (!trimmed) return "Sin PH"
  return trimmed === "Si" ? "Sí" : trimmed
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

function duplicateLabel(coincidencias: CoincidenciaPublicacion[]) {
  const confirmed = coincidencias.filter((item) => item.estado === "confirmada").length
  if (confirmed) return `${confirmed} repetida${confirmed === 1 ? "" : "s"}`
  return `${coincidencias.length} posible${coincidencias.length === 1 ? "" : "s"}`
}

export function PublicacionesManagerPro({
  publicaciones,
  fuentes,
  barrios,
  tiposInmueble,
  hasSinBarrio,
  hasActiveFilters,
}: {
  publicaciones: Row[]
  fuentes: Fuente[]
  barrios: Array<{ value: string; label: string }>
  tiposInmueble: Array<{ value: string; label: string }>
  hasSinBarrio: boolean
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
  const [detailImageDeleting, setDetailImageDeleting] = useState<string | null>(null)
  const [htmlLoading, setHtmlLoading] = useState(false)
  const [notaDraft, setNotaDraft] = useState("")
  const [notaSaving, setNotaSaving] = useState(false)
  const [toDelete, setToDelete] = useState<Row | null>(null)
  const [comparisonRootId, setComparisonRootId] = useState<number | null>(null)
  const [comparisonRows, setComparisonRows] = useState<ComparacionPublicacion[]>([])
  const [comparisonImages, setComparisonImages] = useState<Record<number, ImageItem[]>>({})
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [comparisonToDismiss, setComparisonToDismiss] = useState<ComparisonDismissTarget | null>(null)
  const [comparisonDismissLoading, setComparisonDismissLoading] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const router = useRouter()

  const totalPages = Math.max(1, Math.ceil(publicaciones.length / pageSize))
  const safePage = Math.min(currentPage, totalPages)
  const pageStart = (safePage - 1) * pageSize
  const visiblePublicaciones = publicaciones.slice(pageStart, pageStart + pageSize)

  useEffect(() => {
    setCurrentPage(1)
  }, [publicaciones])

  useEffect(() => {
    let active = true
    const items = visiblePublicaciones.map(rowLinks)

    if (items.length === 0) {
      setLinkStatuses({})
      setLinksLoading(false)
      return
    }

    setLinksLoading(true)
    setLinkStatuses({})

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
  }, [publicaciones, safePage, pageSize])

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

  async function openComparison(row: Row) {
    setDetail(null)
    setComparisonToDismiss(null)
    setComparisonRootId(row.id)
    setComparisonRows([])
    setComparisonImages({})
    setComparisonLoading(true)

    try {
      const rows = await getComparacionPublicaciones(row.id)
      setComparisonRows(rows)
      const imageEntries = await Promise.all(rows.map(async (item) => {
        try {
          const response = await fetch(`/api/publicaciones/${item.id}/imagenes`)
          const data = response.ok ? (await response.json()) as { images?: ImageItem[] } : { images: [] }
          return [item.id, Array.isArray(data.images) ? data.images : []] as const
        } catch {
          return [item.id, []] as const
        }
      }))
      setComparisonImages(Object.fromEntries(imageEntries))
    } catch (error) {
      toast.error("No se pudo abrir la comparacion", {
        description: error instanceof Error ? error.message : "Error desconocido",
      })
      setComparisonRootId(null)
    } finally {
      setComparisonLoading(false)
    }
  }

  async function confirmDismissComparison() {
    const target = comparisonToDismiss
    if (!target || comparisonDismissLoading) return

    setComparisonDismissLoading(true)
    try {
      const result = await descartarCoincidenciaPublicaciones(target.coincidenciaId)
      if (!result.success) {
        toast.error("No se pudo descartar la coincidencia", { description: result.error })
        return
      }

      const remainingRows = comparisonRows.filter((item) => item.id !== target.relatedId)
      setComparisonRows(remainingRows)
      setComparisonImages((current) => {
        const next = { ...current }
        delete next[target.relatedId]
        return next
      })
      setComparisonToDismiss(null)
      if (!remainingRows.some((item) => item.id !== target.rootId)) {
        setComparisonRootId(null)
      }
      toast.success("Publicaciones marcadas como no repetidas", {
        description: `La relacion entre #${target.rootId} y #${target.relatedId} fue descartada.`,
      })
      router.refresh()
    } catch (error) {
      toast.error("No se pudo descartar la coincidencia", {
        description: error instanceof Error ? error.message : "Error desconocido",
      })
    } finally {
      setComparisonDismissLoading(false)
    }
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

  async function deleteDetailImage(image: ImageItem) {
    if (!detail || detailImageDeleting) return
    const confirmed = window.confirm(
      `¿Estás seguro de que deseas eliminar esta imagen?\n\n${image.name}\n\nEsta acción no se puede deshacer.`,
    )
    if (!confirmed) return

    setDetailImageDeleting(image.name)
    try {
      const response = await fetch(
        `/api/publicaciones/${detail.id}/imagenes/${encodeURIComponent(image.name)}`,
        { method: "DELETE" },
      )
      const result = await response.json() as { success?: boolean; error?: string }
      if (!response.ok || !result.success) {
        toast.error(result.error || "No se pudo eliminar la imagen.")
        return
      }
      setDetailImages((current) => current.filter((item) => item.name !== image.name))
      toast.success("Imagen eliminada.")
    } catch {
      toast.error("No se pudo eliminar la imagen.")
    } finally {
      setDetailImageDeleting(null)
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
          <p className="text-sm font-semibold">{publicaciones.length} publicaciones encontradas</p>
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
              Pagina {safePage} de {totalPages} · {publicaciones.length} registros
            </Badge>
          </div>
          <Table className="table-fixed">
              <TableHeader>
                <TableRow className="bg-slate-100/80 dark:bg-zinc-900">
                  <TableHead className="w-14">ID</TableHead>
                  <TableHead className="w-[160px]">Publicacion</TableHead>
                  <TableHead className="w-[110px]">Barrio</TableHead>
                  <TableHead className="w-[90px]">Fuente</TableHead>
                  <TableHead className="w-[130px] text-right">Precio</TableHead>
                  <TableHead className="w-[80px] text-right">Area</TableHead>
                  <TableHead className="w-[90px] text-right">$/m2</TableHead>
                  <TableHead className="w-[110px]">Caracteristicas</TableHead>
                  <TableHead className="w-[180px]">PH</TableHead>
                  <TableHead className="w-[100px]">Nota</TableHead>
                  <TableHead className="w-[100px]">Captura</TableHead>
                  <TableHead className="w-[180px] text-right">Acciones</TableHead>
                </TableRow>
                <PublicacionesColumnFilters fuentes={fuentes} barrios={barrios} tiposInmueble={tiposInmueble} hasSinBarrio={hasSinBarrio} />
              </TableHeader>
              <TableBody>
                {visiblePublicaciones.map((p, index) => (
                  <TableRow
                    key={p.id}
                    className={[
                      "cursor-pointer transition-colors hover:bg-emerald-50/70 dark:hover:bg-emerald-400/10",
                      linkStatuses[p.id]?.ok === false
                        ? "border-red-300 bg-red-50/80 hover:bg-red-100/80 dark:border-red-400/40 dark:bg-red-950/35 dark:hover:bg-red-950/50"
                        : p.coincidencias?.length
                          ? "border-amber-300 bg-amber-50/70 hover:bg-amber-100/70 dark:border-amber-400/30 dark:bg-amber-400/10 dark:hover:bg-amber-400/15"
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
                      {!!p.coincidencias?.length && (
                        <Badge className="mt-1 gap-1 bg-amber-500 text-white hover:bg-amber-500">
                          <AlertTriangle className="size-3" />
                          {duplicateLabel(p.coincidencias)}
                        </Badge>
                      )}
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
                    <TableCell className="text-sm">
                      <ExpandableText text={phLabel(p.ph)} maxWidth={160} truncateLength={30} />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{shortNote(p.notas)}</TableCell>
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
                        {!!p.coincidencias?.length && (
                          <Button variant="outline" size="sm" onClick={() => void openComparison(p)} className="gap-1 border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-400/30 dark:text-amber-300 dark:hover:bg-amber-400/10">
                            <Columns3 className="size-4" />
                            Comparar
                          </Button>
                        )}
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
          <div className="flex flex-col gap-3 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>Mostrar</span>
              <select
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value))
                  setCurrentPage(1)
                }}
                className="h-9 rounded-md border border-input bg-background px-2 text-foreground"
                aria-label="Publicaciones por pagina"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
              <span>por pagina · {pageStart + 1}-{Math.min(pageStart + pageSize, publicaciones.length)} de {publicaciones.length}</span>
            </div>
            <div className="flex items-center justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={safePage <= 1}
                onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                className="gap-1"
              >
                <ChevronLeft className="size-4" />
                Anterior
              </Button>
              <Badge variant="outline">{safePage} / {totalPages}</Badge>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={safePage >= totalPages}
                onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                className="gap-1"
              >
                Siguiente
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>
        </Card>
      )}

      {formOpen && (
        <PublicacionForm
          key={editing ? `edit-${editing.id}` : "create"}
          fuentes={fuentes}
          barrios={barrios}
          tiposInmueble={tiposInmueble}
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

              {!!detail.coincidencias?.length && (
                <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-950 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-100">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-300" />
                    <div>
                      <p className="font-semibold">Esta publicacion puede estar repetida</p>
                      <p className="text-xs opacity-80">El comparador encontro imagenes, ubicacion o caracteristicas coincidentes.</p>
                    </div>
                    <Button type="button" variant="outline" size="sm" className="ml-auto shrink-0 gap-2 border-amber-300 bg-white/70 text-amber-800 hover:bg-white dark:border-amber-400/30 dark:bg-black/10 dark:text-amber-200" onClick={() => void openComparison(detail)}>
                      <Columns3 className="size-4" />
                      Comparar todas
                    </Button>
                  </div>
                  <div className="space-y-2">
                    {detail.coincidencias.map((coincidencia) => (
                      <div key={coincidencia.id} className="flex flex-col gap-2 rounded-md border border-amber-200 bg-white/70 p-3 dark:border-amber-400/20 dark:bg-black/10 sm:flex-row sm:items-center sm:justify-between">
                        <div className="text-sm">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold">Publicacion #{coincidencia.publicacionRelacionadaId}</span>
                            <Badge variant="secondary" className="border border-amber-300/70 bg-amber-100 text-amber-950 dark:border-amber-300/20 dark:bg-amber-300/15 dark:text-amber-100">
                              {coincidencia.fuenteRelacionada || "Fuente desconocida"}
                            </Badge>
                            <span>{coincidencia.puntaje}% de coincidencia</span>
                          </div>
                          <div className="text-xs opacity-75">
                            {coincidencia.estado === "confirmada" ? "Coincidencia confirmada" : "Pendiente de revision"}
                            {coincidencia.imagenesCoincidentes > 0 ? ` · ${coincidencia.imagenesCoincidentes} imagen(es)` : ""}
                          </div>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            const related = publicaciones.find((item) => item.id === coincidencia.publicacionRelacionadaId)
                            if (related) setDetail(related)
                            else router.push(`/?id=${coincidencia.publicacionRelacionadaId}`)
                          }}
                        >
                          Ver relacionada
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <Detail label="Precio" value={formatCOP(detail.precio)} />
                <Detail label="Area" value={formatNumber(detail.m2, " m2")} />
                <Detail label="$/m2" value={formatCOP(detail.precioM2)} />
                <Detail label="Administracion" value={formatCOP(detail.administracion)} />
                <Detail label="Barrio" value={barrioLabel(detail.barrio)} />
                <Detail label="Ciudad" value={detail.ciudad || "-"} />
                <Detail label="PH" value={phLabel(detail.ph)} />
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
                      <div key={image.src} className="group relative overflow-hidden rounded-lg border bg-muted">
                        <a href={image.src} target="_blank" rel="noopener noreferrer" className="block">
                          <img
                            src={thumbSrc(image.src, DETAIL_THUMB_WIDTH)}
                            alt={`Imagen de publicacion ${detail.id}`}
                            className="h-28 w-full object-cover transition group-hover:brightness-75"
                            loading="lazy"
                            decoding="async"
                          />
                        </a>
                        <Button
                          type="button"
                          variant="destructive"
                          size="icon"
                          title="Eliminar imagen"
                          aria-label={`Eliminar ${image.name}`}
                          disabled={detailImageDeleting !== null}
                          onClick={() => void deleteDetailImage(image)}
                          className="absolute right-2 top-2 z-10 size-9 rounded-full border-2 border-white bg-red-600 text-white opacity-0 shadow-lg transition hover:bg-red-700 group-hover:opacity-100 focus-visible:opacity-100"
                        >
                          {detailImageDeleting === image.name
                            ? <Loader2 className="size-5 animate-spin" />
                            : <X className="size-5 stroke-[3]" />}
                        </Button>
                      </div>
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
                  {linkStatuses[detail.id] && linkStatuses[detail.id]?.ok === null && (
                    <Badge variant="outline" className="gap-1 border-slate-300 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                      <HelpCircle className="size-3" />
                      No verificable (sesion Facebook)
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

      <Dialog
        open={comparisonRootId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setComparisonRootId(null)
            setComparisonToDismiss(null)
          }
        }}
      >
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-6xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Columns3 className="size-5 text-emerald-600" />
              Comparar publicaciones repetidas
            </DialogTitle>
            <DialogDescription>
              Revisa imágenes y datos generales lado a lado antes de tomar una decisión.
            </DialogDescription>
          </DialogHeader>

          {comparisonLoading ? (
            <div className="flex min-h-72 items-center justify-center gap-3 text-muted-foreground">
              <Loader2 className="size-5 animate-spin" />
              Cargando publicaciones e imágenes...
            </div>
          ) : comparisonRows.length > 1 ? (
            <div className="grid items-stretch gap-4 md:grid-cols-2 xl:grid-cols-3">
              {comparisonRows.map((item) => {
                const images = comparisonImages[item.id] ?? []
                const isRoot = item.id === comparisonRootId
                return (
                  <article key={item.id} className={`overflow-hidden rounded-xl border bg-background shadow-sm ${isRoot ? "border-emerald-400 ring-2 ring-emerald-400/15" : "border-slate-200 dark:border-white/10"}`}>
                    <ComparisonImageCarousel publicationId={item.id} images={images}>
                      <div className="absolute left-3 top-3 flex flex-wrap gap-2">
                        <Badge className={isRoot ? "bg-emerald-600 text-white" : "bg-black/70 text-white"}>#{item.id}{isRoot ? " · seleccionada" : ""}</Badge>
                        {item.estado && <Badge className={item.estado === "confirmada" ? "bg-emerald-600 text-white" : "bg-amber-500 text-white"}>{item.estado}</Badge>}
                      </div>
                    </ComparisonImageCarousel>
                    <div className="space-y-4 p-4">
                      <div>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="font-semibold">{item.tipoInmueble || "Inmueble"}</h3>
                          <Badge variant="secondary">{item.fuenteNombre || "Sin fuente"}</Badge>
                        </div>
                        <p className="mt-2 text-xl font-bold text-emerald-700 dark:text-emerald-300">{formatCOP(item.precio)}</p>
                        {item.puntaje !== null && <p className="mt-1 text-xs text-muted-foreground">{item.puntaje}% de coincidencia · {item.imagenesCoincidentes} imagen(es) idéntica(s)</p>}
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <CompareValue label="Barrio" value={item.barrio || "-"} />
                        <CompareValue label="Ciudad" value={item.ciudad || "-"} />
                        <CompareValue label="Área" value={formatNumber(item.m2, " m2")} />
                        <CompareValue label="Construida" value={formatNumber(item.m2Construido, " m2")} />
                        <CompareValue label="Habitaciones" value={item.habitaciones ?? "-"} />
                        <CompareValue label="Baños" value={item.banios ?? "-"} />
                        <CompareValue label="Parqueaderos" value={item.parqueadero ?? "-"} />
                        <CompareValue label="Estrato" value={item.estrato ?? "-"} />
                        <CompareValue label="PH" value={item.ph || "-"} className="col-span-2" />
                        <CompareValue label="Dirección" value={item.direccion || "-"} className="col-span-2" />
                      </div>
                      {item.descripcion && <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">{item.descripcion}</p>}
                      <div className="space-y-2">
                        {!isRoot && item.coincidenciaId !== null && (
                          <Button
                            type="button"
                            variant="outline"
                            className="w-full gap-2 border-red-300 text-red-700 hover:border-red-400 hover:bg-red-50 hover:text-red-800 dark:border-red-400/30 dark:text-red-300 dark:hover:bg-red-400/10 dark:hover:text-red-200"
                            onClick={() => {
                              if (comparisonRootId == null || item.coincidenciaId == null) return
                              setComparisonToDismiss({
                                coincidenciaId: item.coincidenciaId,
                                rootId: comparisonRootId,
                                relatedId: item.id,
                              })
                            }}
                          >
                            <CircleX className="size-4" />
                            No es repetida
                          </Button>
                        )}
                        <Button type="button" variant="outline" className="w-full gap-2" onClick={() => window.open(item.linkOrigen, "_blank", "noopener,noreferrer")}>
                          <ExternalLink className="size-4" />
                          Abrir publicación original
                        </Button>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              No se encontraron publicaciones relacionadas para comparar.
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={comparisonToDismiss !== null}
        onOpenChange={(open) => {
          if (!open && !comparisonDismissLoading) setComparisonToDismiss(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CircleX className="size-5 text-red-600 dark:text-red-300" />
              Marcar como no repetidas
            </DialogTitle>
            <DialogDescription>
              Las publicaciones #{comparisonToDismiss?.rootId} y #{comparisonToDismiss?.relatedId} dejarán de aparecer como coincidencia. No se eliminará ninguna publicación ni sus imágenes.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setComparisonToDismiss(null)}
              disabled={comparisonDismissLoading}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void confirmDismissComparison()}
              disabled={comparisonDismissLoading}
              className="gap-2"
            >
              {comparisonDismissLoading ? <Loader2 className="size-4 animate-spin" /> : <CircleX className="size-4" />}
              {comparisonDismissLoading ? "Marcando..." : "Sí, no son repetidas"}
            </Button>
          </DialogFooter>
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

function CompareValue({ label, value, className = "" }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-slate-200/80 bg-slate-50/70 p-2.5 dark:border-white/10 dark:bg-white/5 ${className}`}>
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 break-words font-medium text-foreground">{value}</p>
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
