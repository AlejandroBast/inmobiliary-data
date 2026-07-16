import { readFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import dotenv from "../node_modules/dotenv/lib/main.js"
import mysql from "../node_modules/mysql2/promise.js"

const sourcePath = process.argv[2]
if (!sourcePath) throw new Error("Debes indicar el archivo oficial de barrios y veredas.")
for (const envPath of ["../.env.local", "../.env", ".env.local", ".env"]) {
  dotenv.config({ path: path.resolve(process.cwd(), envPath), override: false, quiet: true })
}

const normalize = (value) => String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
  .toLowerCase().replace(/\b(?:barrio|vereda|corregimiento|sector|urbanizacion|urb)\b/g, " ")
  .replace(/\b(?:et|etapa)\b/g, " ")
  .replace(/\bxxiii\b/g, "23").replace(/\biv\b/g, "4").replace(/\biii\b/g, "3")
  .replace(/\bii\b/g, "2").replace(/\bi\b/g, "1").replace(/\bcabecera\b/g, " ")
  .replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim()

function parseSource(text) {
  const aliases = []
  const urban = new Set()
  const rural = new Set()
  for (const line of text.split(/\r?\n/)) {
    const parts = line.split("\t").map((part) => part.trim()).filter(Boolean)
    if (parts[0] === "Comuna:" && parts[2] === "Barrio:") {
      const canonical = parts.slice(3).join(" ").trim()
      if (canonical) { urban.add(canonical); aliases.push({ alias: canonical, canonical, type: "barrio" }) }
    } else if (parts[0] === "Corregimiento:" && parts[2] === "Vereda:") {
      const canonical = parts[1]
      const vereda = parts.slice(3).join(" ").trim()
      if (canonical && vereda) {
        rural.add(canonical)
        aliases.push({ alias: canonical, canonical, type: "corregimiento" })
      }
    }
  }
  const unique = [...new Map(aliases.map((item) => [`${normalize(item.alias)}:${normalize(item.canonical)}`, item])).values()]
    .filter((item) => normalize(item.alias))
    .sort((a, b) => normalize(b.alias).length - normalize(a.alias).length)
  return { aliases: unique, urban: urban.size, rural: rural.size }
}

function candidates(text, catalog, preferCanonical = false) {
  const source = ` ${normalize(text)} `
  if (!source.trim()) return []
  if (preferCanonical) {
    const exactUrban = catalog.find((item) => item.type === "barrio" && normalize(item.canonical) === normalize(text))
    if (exactUrban) return [exactUrban]
    const exactRural = catalog.find((item) => item.type === "corregimiento" && normalize(item.canonical) === normalize(text))
    if (exactRural) return [exactRural]
  }
  const normalizedInput = normalize(text)
  const found = catalog.filter((item) =>
    item.type === "corregimiento"
      ? normalizedInput === normalize(item.alias)
      : source.includes(` ${normalize(item.alias)} `),
  )
  if (!found.length) return []
  const longest = Math.max(...found.map((item) => normalize(item.alias).length))
  return [...new Map(found.filter((item) => normalize(item.alias).length === longest)
    .map((item) => [normalize(item.canonical), item])).values()]
}

function explicitLocationText(row) {
  const text = [row.direccion, row.descripcion].filter(Boolean).join("\n")
  const fragments = []
  const pattern = /(?:barrio|vereda|corregimiento|ubicad[oa]\s+en|sector)\s+(?:de\s+|el\s+|la\s+)?([^\n,.;]{2,80})/gi
  for (const match of text.matchAll(pattern)) fragments.push(match[1])
  return fragments.join("\n")
}

const parsed = parseSource(await readFile(path.resolve(sourcePath), "utf8"))
const pool = mysql.createPool({ host: process.env.DB_HOST ?? "localhost", port: Number(process.env.DB_PORT ?? 3306), user: process.env.DB_USER ?? "root", password: process.env.DB_PASSWORD ?? "", database: process.env.DB_NAME ?? "db_inmobiliary_data", connectionLimit: 2 })
const [rows] = await pool.query("SELECT id, barrio, direccion, ph, descripcion FROM publicaciones ORDER BY id")
await pool.end()

const result = { directas: 0, descripcionExplicita: 0, textoGeneral: 0, ambiguas: 0, sinCoincidencia: 0 }
const examples = { generalizadas: [], descripcion: [], textoGeneral: [], ambiguas: [], sinCoincidencia: [] }
for (const row of rows) {
  const direct = candidates(row.barrio, parsed.aliases, true)
  const description = direct.length ? [] : candidates(explicitLocationText(row), parsed.aliases)
  const generalText = direct.length || description.length ? [] : candidates([row.ph, row.descripcion].filter(Boolean).join("\n"), parsed.aliases)
  const selected = direct.length ? direct : description.length ? description : generalText
  if (selected.length === 1) {
    if (direct.length) result.directas += 1
    else if (description.length) result.descripcionExplicita += 1
    else result.textoGeneral += 1
    const item = selected[0]
    if (normalize(row.barrio) !== normalize(item.canonical) && examples.generalizadas.length < 40) {
      examples.generalizadas.push({ id: row.id, actual: row.barrio, resultado: item.canonical, detectadoPor: item.type })
    }
    if (!direct.length && examples.descripcion.length < 25) examples.descripcion.push({ id: row.id, actual: row.barrio, resultado: item.canonical })
    if (generalText.length && examples.textoGeneral.length < 40) examples.textoGeneral.push({ id: row.id, actual: row.barrio, resultado: item.canonical })
  } else if (selected.length > 1) {
    result.ambiguas += 1
    if (examples.ambiguas.length < 20) examples.ambiguas.push({ id: row.id, actual: row.barrio, candidatos: selected.map((item) => item.canonical) })
  } else {
    result.sinCoincidencia += 1
    examples.sinCoincidencia.push({ id: row.id, actual: row.barrio })
  }
}

console.log(JSON.stringify({ catalogo: { barriosUrbanos: parsed.urban, corregimientos: parsed.rural, aliasTotales: parsed.aliases.length }, publicaciones: { total: rows.length, ...result }, ejemplos: examples }, null, 2))
