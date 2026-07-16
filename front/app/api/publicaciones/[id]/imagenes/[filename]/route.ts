import { access, readFile, unlink } from "fs/promises"
import path from "path"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

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

export async function GET(_: Request, { params }: { params: Promise<{ id: string; filename: string }> }) {
  const { id, filename } = await params
  const imagePath = getImagePath(id, filename)
  if (!imagePath) return new NextResponse("Invalid image path", { status: 400 })

  try {
    await access(imagePath)
  } catch {
    return new NextResponse("Not found", { status: 404 })
  }

  const file = await readFile(imagePath)
  return new NextResponse(file, {
    headers: {
      "Content-Type": contentType(filename),
      "Cache-Control": "public, max-age=3600",
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
    return NextResponse.json({ success: true })
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? String(error.code) : ""
    if (code === "ENOENT") {
      return NextResponse.json({ success: false, error: "La imagen ya no existe." }, { status: 404 })
    }
    return NextResponse.json({ success: false, error: "No se pudo eliminar la imagen." }, { status: 500 })
  }
}
