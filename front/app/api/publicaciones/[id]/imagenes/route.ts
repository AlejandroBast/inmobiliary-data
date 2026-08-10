import { NextResponse } from "next/server"
import path from "path"
import { access, mkdir, readdir, writeFile } from "fs/promises"

export const runtime = "nodejs"

const MAX_FILE_BYTES = 15 * 1024 * 1024
const IMAGE_EXT_RE = /\.(png|jpe?g|webp|gif)$/i

function getImagesDir(publicacionId: string) {
  return path.resolve(process.cwd(), "..", "evidencias", `publicacion_${publicacionId}`, "imagenes")
}

// Nunca se usa el nombre del archivo del cliente tal cual en la ruta final:
// solo se conservan letras/numeros/guiones (y la extension, validada aparte),
// para no arrastrar separadores de ruta ni caracteres raros al filesystem.
function sanitizeBaseName(filename: string) {
  const base = path.basename(filename, path.extname(filename))
  const cleaned = base.replace(/[^a-zA-Z0-9\-_]+/g, "_").replace(/^_+|_+$/g, "")
  return cleaned.slice(0, 80) || "imagen"
}

async function pathExists(candidate: string) {
  try {
    await access(candidate)
    return true
  } catch {
    return false
  }
}

async function uniqueFilename(imagesDir: string, base: string, ext: string) {
  let filename = `${base}${ext}`
  let counter = 1
  while (await pathExists(path.join(imagesDir, filename))) {
    filename = `${base}_${counter}${ext}`
    counter += 1
  }
  return filename
}

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const imagesDir = getImagesDir(id)

  try {
    await access(imagesDir)
  } catch {
    return NextResponse.json({ images: [] })
  }

  const entries = await readdir(imagesDir, { withFileTypes: true })
  const images = entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((name) => IMAGE_EXT_RE.test(name))
    .map((name) => ({
      name,
      src: `/api/publicaciones/${id}/imagenes/${encodeURIComponent(name)}`,
    }))

  return NextResponse.json({ images })
}

// Carga manual de imagenes (crear o editar publicacion). Los scrapers dejan
// sus capturas directamente en evidencias/publicacion_<id>/imagenes/; esto
// permite que el cliente agregue las suyas a la misma carpeta desde el front.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  if (!/^\d+$/.test(id)) {
    return NextResponse.json({ success: false, error: "ID de publicacion invalido." }, { status: 400 })
  }

  const formData = await request.formData()
  const files = formData.getAll("files").filter((value): value is File => value instanceof File)
  if (files.length === 0) {
    return NextResponse.json({ success: false, error: "No se recibio ninguna imagen." }, { status: 400 })
  }

  const imagesDir = getImagesDir(id)
  await mkdir(imagesDir, { recursive: true })

  const saved: Array<{ name: string; src: string }> = []
  const skipped: string[] = []

  for (const file of files) {
    const ext = path.extname(file.name).toLowerCase()
    if (!IMAGE_EXT_RE.test(`x${ext}`) || file.size === 0) {
      skipped.push(file.name)
      continue
    }
    if (file.size > MAX_FILE_BYTES) {
      skipped.push(file.name)
      continue
    }

    const base = sanitizeBaseName(file.name)
    const filename = await uniqueFilename(imagesDir, base, ext)
    const buffer = Buffer.from(await file.arrayBuffer())
    await writeFile(path.join(imagesDir, filename), buffer)
    saved.push({ name: filename, src: `/api/publicaciones/${id}/imagenes/${encodeURIComponent(filename)}` })
  }

  if (saved.length === 0) {
    return NextResponse.json(
      { success: false, error: "Ningun archivo era una imagen valida (png/jpg/webp/gif, maximo 15MB)." },
      { status: 400 },
    )
  }

  return NextResponse.json({ success: true, images: saved, skipped })
}