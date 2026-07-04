import { access, readFile } from "fs/promises"
import path from "path"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

function getImagePath(publicacionId: string, filename: string) {
  return path.resolve(process.cwd(), "..", "evidencias", `publicacion_${publicacionId}`, "imagenes", filename)
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