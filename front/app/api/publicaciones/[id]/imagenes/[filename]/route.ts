import { access, mkdir, readFile, readdir, unlink, writeFile } from "fs/promises"
import path from "path"
import sharp from "sharp"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

const THUMBS_DIRNAME = ".thumbs"
const MAX_THUMB_WIDTH = 1600

function getImagePath(publicacionId: string, filename: string) {
  if (!/^\d+$/.test(publicacionId) || filename !== path.basename(filename)) return null
  if (!/\.(png|jpe?g|webp|gif)$/i.test(filename)) return null
  const imagesDir = path.resolve(process.cwd(), "..", "evidencias", `publicacion_${publicacionId}`, "imagenes")
  const imagePath = path.resolve(imagesDir, filename)
  return imagePath.startsWith(`${imagesDir}${path.sep}`) ? imagePath : null
}

function contentType(filename: string) {
  const lower = filename.toLowerCase()
  if (lower.endsWith(".png")) return "image/png"
  if (lower.endsWith(".webp")) return "image/webp"
  if (lower.endsWith(".gif")) return "image/gif"
  return "image/jpeg"
}

function thumbFileName(filename: string, width: number) {
  const ext = path.extname(filename)
  const base = path.basename(filename, ext)
  return `${base}_w${width}.webp`
}

async function getOrCreateThumbnail(imagesDir: string, filename: string, width: number) {
  const thumbsDir = path.join(imagesDir, THUMBS_DIRNAME)
  const thumbPath = path.join(thumbsDir, thumbFileName(filename, width))

  try {
    return await readFile(thumbPath)
  } catch {
    // not cached yet, fall through and generate it
  }

  const original = await readFile(path.join(imagesDir, filename))
  const resized = await sharp(original)
    .rotate()
    .resize({ width, withoutEnlargement: true })
    .webp({ quality: 72 })
    .toBuffer()

  try {
    await mkdir(thumbsDir, { recursive: true })
    await writeFile(thumbPath, resized)
  } catch {
    // caching to disk is best-effort; still return the resized buffer
  }

  return resized
}

async function deleteThumbnails(imagesDir: string, filename: string) {
  const thumbsDir = path.join(imagesDir, THUMBS_DIRNAME)
  const ext = path.extname(filename)
  const base = path.basename(filename, ext)
  try {
    const entries = await readdir(thumbsDir)
    await Promise.all(
      entries
        .filter((entry) => entry.startsWith(`${base}_w`))
        .map((entry) => unlink(path.join(thumbsDir, entry)).catch(() => undefined)),
    )
  } catch {
    // no thumbs directory or nothing to clean up
  }
}

export async function GET(request: Request, { params }: { params: Promise<{ id: string; filename: string }> }) {
  const { id, filename } = await params
  const imagePath = getImagePath(id, filename)
  if (!imagePath) return new NextResponse("Invalid image path", { status: 400 })

  try {
    await access(imagePath)
  } catch {
    return new NextResponse("Not found", { status: 404 })
  }

  const requestedWidth = Number(new URL(request.url).searchParams.get("w"))
  const width = Number.isFinite(requestedWidth) && requestedWidth > 0
    ? Math.min(Math.round(requestedWidth), MAX_THUMB_WIDTH)
    : null

  if (width) {
    try {
      const thumbnail = await getOrCreateThumbnail(path.dirname(imagePath), filename, width)
      return new NextResponse(thumbnail, {
        headers: {
          "Content-Type": "image/webp",
          "Cache-Control": "public, max-age=31536000, immutable",
        },
      })
    } catch {
      // if resizing fails for any reason, fall back to serving the original below
    }
  }

  const file = await readFile(imagePath)
  return new NextResponse(file, {
    headers: {
      "Content-Type": contentType(filename),
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  })
}

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string; filename: string }> }) {
  const { id, filename } = await params
  const imagePath = getImagePath(id, filename)
  if (!imagePath) {
    return NextResponse.json({ success: false, error: "La imagen seleccionada no es valida." }, { status: 400 })
  }
  try {
    await unlink(imagePath)
    await deleteThumbnails(path.dirname(imagePath), filename)
    return NextResponse.json({ success: true })
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? String(error.code) : ""
    if (code === "ENOENT") {
      return NextResponse.json({ success: false, error: "La imagen ya no existe." }, { status: 404 })
    }
    return NextResponse.json({ success: false, error: "No se pudo eliminar la imagen." }, { status: 500 })
  }
}
