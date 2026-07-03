import { NextResponse } from "next/server"
import path from "path"
import { access, readdir } from "fs/promises"

export const runtime = "nodejs"

function getImagesDir(publicacionId: string) {
  return path.resolve(process.cwd(), "..", "evidencias", `publicacion_${publicacionId}`, "imagenes")
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
    .filter((name) => /\.(png|jpe?g|webp|gif)$/i.test(name))
    .map((name) => ({
      name,
      src: `/api/publicaciones/${id}/imagenes/${encodeURIComponent(name)}`,
    }))

  return NextResponse.json({ images })
}