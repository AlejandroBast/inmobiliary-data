import { NextResponse } from "next/server"
import path from "path"
import { access, readdir } from "fs/promises"

export const runtime = "nodejs"

function getHtmlDir(publicacionId: string) {
  return path.resolve(process.cwd(), "..", "evidencias", `publicacion_${publicacionId}`, "html")
}

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const htmlDir = getHtmlDir(id)

  try {
    await access(htmlDir)
  } catch {
    return NextResponse.json({ html: [] })
  }

  const entries = await readdir(htmlDir, { withFileTypes: true })
  const html = entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((name) => /\.html?$/i.test(name))
    .map((name) => ({
      name,
      src: `/api/publicaciones/${id}/html/${encodeURIComponent(name)}`,
    }))

  return NextResponse.json({ html })
}