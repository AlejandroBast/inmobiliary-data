import { access, readFile } from "fs/promises"
import path from "path"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

function getHtmlPath(publicacionId: string, filename: string) {
  return path.resolve(process.cwd(), "..", "evidencias", `publicacion_${publicacionId}`, "html", filename)
}

export async function GET(_: Request, { params }: { params: Promise<{ id: string; filename: string }> }) {
  const { id, filename } = await params
  const htmlPath = getHtmlPath(id, filename)

  try {
    await access(htmlPath)
  } catch {
    return new NextResponse("Not found", { status: 404 })
  }

  const file = await readFile(htmlPath)
  return new NextResponse(file, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  })
}