import { NextResponse } from "next/server"

export const runtime = "nodejs"

const MAX_FILE_BYTES = 15 * 1024 * 1024
const FETCH_TIMEOUT_MS = 15000
const CONTENT_TYPE_EXT: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  // Metrocuadrado responde con este content-type no estandar.
  "image/jpg": "jpg",
  "image/pjpeg": "jpg",
  "image/webp": "webp",
  "image/gif": "gif",
}

// Bloqueo basico de red interna: este endpoint descarga cualquier URL que
// pida un usuario ya logueado, asi que evita que apunte a la propia maquina
// o a rangos privados (SSRF).
function isBlockedHost(hostname: string) {
  const host = hostname.toLowerCase()
  if (host === "localhost" || host.endsWith(".localhost")) return true
  if (host === "0.0.0.0" || host === "::1") return true
  if (/^127\./.test(host)) return true
  if (/^10\./.test(host)) return true
  if (/^192\.168\./.test(host)) return true
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(host)) return true
  if (/^169\.254\./.test(host)) return true
  return false
}

// Permite arrastrar una imagen directamente desde otra pestaña del navegador
// (ej. Facebook) sin exportarla antes: el cliente solo tiene la URL de la
// imagen (dataTransfer no trae los bytes en ese caso), asi que el backend la
// descarga el mismo evitando el bloqueo de CORS que tendria el fetch del cliente.
export async function POST(request: Request) {
  let body: { url?: string }
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: "Solicitud invalida." }, { status: 400 })
  }

  const rawUrl = body.url?.trim()
  if (!rawUrl) {
    return NextResponse.json({ error: "Falta la URL de la imagen." }, { status: 400 })
  }

  let target: URL
  try {
    target = new URL(rawUrl)
  } catch {
    return NextResponse.json({ error: "URL invalida." }, { status: 400 })
  }

  if (target.protocol !== "http:" && target.protocol !== "https:") {
    return NextResponse.json({ error: "Solo se admiten URLs http/https." }, { status: 400 })
  }
  if (isBlockedHost(target.hostname)) {
    return NextResponse.json({ error: "No se permite esa direccion." }, { status: 400 })
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(target, {
      signal: controller.signal,
      redirect: "follow",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        Accept: "image/*",
      },
    })
  } catch {
    return NextResponse.json({ error: "No se pudo descargar la imagen." }, { status: 400 })
  } finally {
    clearTimeout(timeout)
  }

  if (!response.ok) {
    return NextResponse.json({ error: `La imagen respondio con estado ${response.status}.` }, { status: 400 })
  }

  const contentType = response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() ?? ""
  const ext = CONTENT_TYPE_EXT[contentType]
  if (!ext) {
    return NextResponse.json({ error: "El enlace no apunta a una imagen valida (png/jpg/webp/gif)." }, { status: 400 })
  }

  const contentLength = Number(response.headers.get("content-length") ?? "0")
  if (contentLength > MAX_FILE_BYTES) {
    return NextResponse.json({ error: "La imagen supera el tamaño maximo (15MB)." }, { status: 400 })
  }

  const buffer = Buffer.from(await response.arrayBuffer())
  if (buffer.byteLength > MAX_FILE_BYTES) {
    return NextResponse.json({ error: "La imagen supera el tamaño maximo (15MB)." }, { status: 400 })
  }
  if (buffer.byteLength === 0) {
    return NextResponse.json({ error: "La imagen esta vacia." }, { status: 400 })
  }

  return new NextResponse(buffer, {
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `inline; filename="imagen_importada.${ext}"`,
      "Cache-Control": "no-store",
    },
  })
}
