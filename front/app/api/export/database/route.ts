import { db } from "@/lib/db"
import { fuentesInmobiliarias, publicaciones } from "@/lib/db/schema"
import { desc, eq } from "drizzle-orm"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

type CellValue = unknown

function escapeXml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;")
}

function normalizeValue(value: CellValue) {
  if (value === null || value === undefined) return ""
  if (value instanceof Date) return value.toISOString()
  if (Array.isArray(value)) return JSON.stringify(value)
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function columnName(index: number) {
  let name = ""
  let current = index

  while (current > 0) {
    const remainder = (current - 1) % 26
    name = String.fromCharCode(65 + remainder) + name
    current = Math.floor((current - 1) / 26)
  }

  return name
}

function worksheetXml(headers: string[], rows: CellValue[][]) {
  const allRows = [headers, ...rows]
  const sheetRows = allRows
    .map((row, rowIndex) => {
      const rowNumber = rowIndex + 1
      const cells = row
        .map((value, columnIndex) => {
          const cellRef = `${columnName(columnIndex + 1)}${rowNumber}`
          return `<c r="${cellRef}" t="inlineStr"><is><t>${escapeXml(normalizeValue(value))}</t></is></c>`
        })
        .join("")

      return `<row r="${rowNumber}">${cells}</row>`
    })
    .join("")

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>${sheetRows}</sheetData>
</worksheet>`
}

const crcTable = Array.from({ length: 256 }, (_, index) => {
  let crc = index
  for (let bit = 0; bit < 8; bit += 1) {
    crc = crc & 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1
  }
  return crc >>> 0
})

function crc32(buffer: Buffer) {
  let crc = 0xffffffff
  for (const byte of buffer) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

function createZip(files: Array<{ path: string; content: string }>) {
  const localParts: Buffer[] = []
  const centralParts: Buffer[] = []
  let offset = 0

  for (const file of files) {
    const name = Buffer.from(file.path, "utf8")
    const data = Buffer.from(file.content, "utf8")
    const crc = crc32(data)

    const localHeader = Buffer.alloc(30)
    localHeader.writeUInt32LE(0x04034b50, 0)
    localHeader.writeUInt16LE(20, 4)
    localHeader.writeUInt16LE(0, 6)
    localHeader.writeUInt16LE(0, 8)
    localHeader.writeUInt16LE(0, 10)
    localHeader.writeUInt16LE(0, 12)
    localHeader.writeUInt32LE(crc, 14)
    localHeader.writeUInt32LE(data.length, 18)
    localHeader.writeUInt32LE(data.length, 22)
    localHeader.writeUInt16LE(name.length, 26)
    localHeader.writeUInt16LE(0, 28)

    localParts.push(localHeader, name, data)

    const centralHeader = Buffer.alloc(46)
    centralHeader.writeUInt32LE(0x02014b50, 0)
    centralHeader.writeUInt16LE(20, 4)
    centralHeader.writeUInt16LE(20, 6)
    centralHeader.writeUInt16LE(0, 8)
    centralHeader.writeUInt16LE(0, 10)
    centralHeader.writeUInt16LE(0, 12)
    centralHeader.writeUInt16LE(0, 14)
    centralHeader.writeUInt32LE(crc, 16)
    centralHeader.writeUInt32LE(data.length, 20)
    centralHeader.writeUInt32LE(data.length, 24)
    centralHeader.writeUInt16LE(name.length, 28)
    centralHeader.writeUInt16LE(0, 30)
    centralHeader.writeUInt16LE(0, 32)
    centralHeader.writeUInt16LE(0, 34)
    centralHeader.writeUInt16LE(0, 36)
    centralHeader.writeUInt32LE(0, 38)
    centralHeader.writeUInt32LE(offset, 42)

    centralParts.push(centralHeader, name)
    offset += localHeader.length + name.length + data.length
  }

  const centralDirectory = Buffer.concat(centralParts)
  const localFiles = Buffer.concat(localParts)
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0)
  end.writeUInt16LE(0, 4)
  end.writeUInt16LE(0, 6)
  end.writeUInt16LE(files.length, 8)
  end.writeUInt16LE(files.length, 10)
  end.writeUInt32LE(centralDirectory.length, 12)
  end.writeUInt32LE(localFiles.length, 16)
  end.writeUInt16LE(0, 20)

  return Buffer.concat([localFiles, centralDirectory, end])
}

function workbookFile(publicacionesRows: CellValue[][], fuentesRows: CellValue[][]) {
  return createZip([
    {
      path: "[Content_Types].xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`,
    },
    {
      path: "_rels/.rels",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`,
    },
    {
      path: "xl/workbook.xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Publicaciones" sheetId="1" r:id="rId1"/>
    <sheet name="Fuentes" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>`,
    },
    {
      path: "xl/_rels/workbook.xml.rels",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>`,
    },
    {
      path: "xl/worksheets/sheet1.xml",
      content: worksheetXml(
        [
          "ID",
          "Fuente ID",
          "Fuente",
          "Codigo externo",
          "Link origen",
          "Links adicionales",
          "Fecha captura",
          "Coordenadas",
          "Latitud",
          "Longitud",
          "Direccion",
          "Ciudad",
          "Barrio",
          "Tipo inmueble",
          "PH",
          "Estrato",
          "Descripcion",
          "Precio",
          "M2",
          "Precio M2",
          "M2 construido",
          "Precio M2 construido",
          "Antiguedad",
          "Pisos",
          "Habitaciones",
          "Banos",
          "Parqueadero",
          "Administracion",
          "Notas",
        ],
        publicacionesRows,
      ),
    },
    {
      path: "xl/worksheets/sheet2.xml",
      content: worksheetXml(["ID", "Nombre", "URL base", "Tipo fuente", "Activa", "Descripcion"], fuentesRows),
    },
  ])
}

export async function GET() {
  const [publicacionesRows, fuentesRows] = await Promise.all([
    db
      .select({
        id: publicaciones.id,
        fuenteId: publicaciones.fuenteId,
        fuenteNombre: fuentesInmobiliarias.nombre,
        codigoExterno: publicaciones.codigoExterno,
        linkOrigen: publicaciones.linkOrigen,
        linksAdicionales: publicaciones.linksAdicionales,
        fechaCaptura: publicaciones.fechaCaptura,
        coordenadas: publicaciones.coordenadas,
        latitud: publicaciones.latitud,
        longitud: publicaciones.longitud,
        direccion: publicaciones.direccion,
        ciudad: publicaciones.ciudad,
        barrio: publicaciones.barrio,
        tipoInmueble: publicaciones.tipoInmueble,
        ph: publicaciones.ph,
        estrato: publicaciones.estrato,
        descripcion: publicaciones.descripcion,
        precio: publicaciones.precio,
        m2: publicaciones.m2,
        precioM2: publicaciones.precioM2,
        m2Construido: publicaciones.m2Construido,
        precioM2Construido: publicaciones.precioM2Construido,
        antiguedad: publicaciones.antiguedad,
        pisos: publicaciones.pisos,
        habitaciones: publicaciones.habitaciones,
        banios: publicaciones.banios,
        parqueadero: publicaciones.parqueadero,
        administracion: publicaciones.administracion,
        notas: publicaciones.notas,
      })
      .from(publicaciones)
      .leftJoin(fuentesInmobiliarias, eq(publicaciones.fuenteId, fuentesInmobiliarias.id))
      .orderBy(desc(publicaciones.fechaCaptura)),
    db.select().from(fuentesInmobiliarias).orderBy(fuentesInmobiliarias.nombre),
  ])

  const workbook = workbookFile(
    publicacionesRows.map((row) => [
      row.id,
      row.fuenteId,
      row.fuenteNombre,
      row.codigoExterno,
      row.linkOrigen,
      row.linksAdicionales,
      row.fechaCaptura,
      row.coordenadas,
      row.latitud,
      row.longitud,
      row.direccion,
      row.ciudad,
      row.barrio,
      row.tipoInmueble,
      row.ph,
      row.estrato,
      row.descripcion,
      row.precio,
      row.m2,
      row.precioM2,
      row.m2Construido,
      row.precioM2Construido,
      row.antiguedad,
      row.pisos,
      row.habitaciones,
      row.banios,
      row.parqueadero,
      row.administracion,
      row.notas,
    ]),
    fuentesRows.map((row) => [row.id, row.nombre, row.urlBase, row.tipoFuente, row.activa, row.descripcion]),
  )

  const filename = `inmobiliaria_datos_${new Date().toISOString().slice(0, 10)}.xlsx`

  return new Response(workbook, {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  })
}
