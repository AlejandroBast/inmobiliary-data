"use client"

import type React from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { ChevronLeft, ChevronRight, X } from "lucide-react"

type LightboxImage = { name: string; src: string }

// Visor ampliado de las imagenes de una publicacion, sobre la pagina actual.
// Se apila encima de otros dialogos (detalle, comparacion): ESC cierra solo
// este visor. El indice lo controla el llamador para que, por ejemplo, el
// carrusel de la comparacion quede en la foto donde se cerro el visor.
export function ImageLightbox({
  images,
  index,
  onIndexChange,
  onClose,
  title,
}: {
  images: LightboxImage[]
  index: number | null
  onIndexChange: (index: number) => void
  onClose: () => void
  title: string
}) {
  const count = images.length
  const open = index !== null && count > 0
  const safeIndex = open ? ((index % count) + count) % count : 0
  const image = images[safeIndex]

  function move(direction: -1 | 1) {
    if (count <= 1) return
    onIndexChange((safeIndex + direction + count) % count)
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowLeft") {
      event.preventDefault()
      move(-1)
    } else if (event.key === "ArrowRight") {
      event.preventDefault()
      move(1)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        showCloseButton={false}
        onKeyDown={handleKeyDown}
        className="flex h-[calc(100dvh-2rem)] max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden bg-black/95 p-0 text-white ring-white/10 sm:max-w-[calc(100%-4rem)]"
      >
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <DialogTitle className="truncate text-sm font-medium text-white">{title}</DialogTitle>
          <div className="flex shrink-0 items-center gap-3">
            {count > 0 && (
              <span className="text-xs text-white/70">
                {safeIndex + 1} / {count}
              </span>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Cerrar visor"
              className="rounded-full text-white hover:bg-white/15 hover:text-white"
              onClick={onClose}
            >
              <X className="size-5" />
            </Button>
          </div>
        </div>

        <div className="relative flex min-h-0 flex-1 items-center justify-center px-4 pb-4 sm:px-16">
          {image && (
            <img
              key={image.src}
              src={image.src}
              alt={`${title} - imagen ${safeIndex + 1}`}
              className="max-h-full max-w-full select-none object-contain"
              decoding="async"
              draggable={false}
            />
          )}

          {count > 1 && (
            <>
              <Button
                type="button"
                variant="secondary"
                size="icon"
                aria-label="Imagen anterior"
                className="absolute left-3 top-1/2 size-11 -translate-y-1/2 rounded-full border border-white/30 bg-black/55 text-white shadow-lg backdrop-blur hover:bg-black/75 hover:text-white"
                onClick={() => move(-1)}
              >
                <ChevronLeft className="size-6" />
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="icon"
                aria-label="Imagen siguiente"
                className="absolute right-3 top-1/2 size-11 -translate-y-1/2 rounded-full border border-white/30 bg-black/55 text-white shadow-lg backdrop-blur hover:bg-black/75 hover:text-white"
                onClick={() => move(1)}
              >
                <ChevronRight className="size-6" />
              </Button>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
