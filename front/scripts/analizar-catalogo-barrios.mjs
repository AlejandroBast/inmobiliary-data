import { readFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import dotenv from "../node_modules/dotenv/lib/main.js"
import mysql from "../node_modules/mysql2/promise.js"

const catalogPath = process.argv[2]
if (!catalogPath) throw new Error("Uso: node scripts/analizar-catalogo-barrios.mjs <catalogo.txt>")

for (const envPath of ["../.env.local", "../.env", ".env.local", ".env"]) {
  dotenv.config({ path: path.resolve(process.cwd(), envPath), override: false, quiet: true })
}

function normalize(value) {
  return String(value ?? "")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim()
}

function parseCatalog(text) {
  const records = []
  const sectionPattern = /Comuna\s+(\d+)\s+[^\r\n]*\r?\n\r?\n([\s\S]*?)(?=\r?\n\r?\nComuna\s+\d+|\r?\n\r?\nPara tu software|$)/gi
  for (const match of text.matchAll(sectionPattern)) {
    const comuna = Number(match[1])
    const list = match[2].replace(/[.\s]+$/, "").replace(/\s+y\s+([^,]+)$/i, ", $1")
    for (const rawName of list.split(",")) {
      const name = rawName.trim()
      if (name) records.push({ name, normalized: normalize(name), comuna })
    }
  }
  return records
}

function findMatches(text, catalog) {
  const normalizedText = ` ${normalize(text)} `
  if (normalizedText.trim().length === 0) return []
  const matches = catalog.filter((item) => normalizedText.includes(` ${item.normalized} `))
  const longest = Math.max(0, ...matches.map((item) => item.normalized.length))
  return matches.filter((item) => item.normalized.length === longest)
}

const text = await readFile(path.resolve(catalogPath), "utf8")
const parsedCatalog = parseCatalog(text)
const uniqueCatalog = [...new Map(parsedCatalog.map((item) => [`${item.comuna}:${item.normalized}`, item])).values()]
const pool = mysql.createPool({
  host: process.env.DB_HOST ?? "localhost",
  port: Number(process.env.DB_PORT ?? 3306),
  user: process.env.DB_USER ?? "root",
  password: process.env.DB_PASSWORD ?? "",
  database: process.env.DB_NAME ?? "db_inmobiliary_data",
  connectionLimit: 2,
})

const [rows] = await pool.query(`SELECT id, barrio, direccion, ph, descripcion FROM publicaciones ORDER BY id`)
await pool.end()

let barrioMatch = 0
let barrioCanonicalExact = 0
let barrioExtended = 0
let textRecovery = 0
let ambiguous = 0
const unmatched = []
const corrections = []
const ambiguityExamples = []

for (const row of rows) {
  const barrioMatches = findMatches(row.barrio, uniqueCatalog)
  const context = [row.direccion, row.ph, row.descripcion].filter(Boolean).join(" ")
  const contextMatches = findMatches(context, uniqueCatalog)
  const selected = barrioMatches.length ? barrioMatches : contextMatches
  if (selected.length === 1) {
    if (barrioMatches.length) {
      barrioMatch += 1
      if (normalize(row.barrio) === selected[0].normalized) barrioCanonicalExact += 1
      else barrioExtended += 1
    } else textRecovery += 1
    if (normalize(row.barrio) !== selected[0].normalized && corrections.length < 30) {
      corrections.push({ id: row.id, actual: row.barrio, detectado: selected[0].name, comuna: selected[0].comuna, origen: barrioMatches.length ? "barrio" : "texto" })
    }
  } else if (selected.length > 1) {
    ambiguous += 1
    if (ambiguityExamples.length < 15) ambiguityExamples.push({ id: row.id, actual: row.barrio, candidatos: selected.map((item) => `${item.name} (C${item.comuna})`) })
  } else {
    unmatched.push({ id: row.id, barrio: row.barrio })
  }
}

const normalizedNames = new Map()
for (const item of uniqueCatalog) {
  const entries = normalizedNames.get(item.normalized) ?? []
  entries.push(item)
  normalizedNames.set(item.normalized, entries)
}
const repeatedNames = [...normalizedNames.values()].filter((items) => items.length > 1)
const riskyShortNames = [...normalizedNames.values()].flat().filter((item) => item.normalized.length <= 5)

console.log(JSON.stringify({
  catalogo: { registros: uniqueCatalog.length, nombresRepetidosEntreComunas: repeatedNames.map((items) => items.map((item) => `${item.name} (C${item.comuna})`)), nombresCortosRiesgosos: riskyShortNames.map((item) => item.name) },
  publicaciones: { total: rows.length, identificadasDesdeBarrio: barrioMatch, yaCanonicas: barrioCanonicalExact, barrioExtendidoCorregible: barrioExtended, candidatasDesdeTextoNoSeguras: textRecovery, ambiguas: ambiguous, sinCoincidencia: rows.length - barrioMatch - textRecovery - ambiguous },
  ejemplosCorreccion: corrections,
  ejemplosAmbiguos: ambiguityExamples,
  ejemplosSinCoincidencia: unmatched,
}, null, 2))
