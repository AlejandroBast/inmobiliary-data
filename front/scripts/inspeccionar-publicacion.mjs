import path from "node:path"
import process from "node:process"
import dotenv from "../node_modules/dotenv/lib/main.js"
import mysql from "../node_modules/mysql2/promise.js"

for (const envPath of ["../.env.local", "../.env", ".env.local", ".env"]) {
  dotenv.config({ path: path.resolve(process.cwd(), envPath), override: false, quiet: true })
}

const id = Number(process.argv[2])
if (!Number.isInteger(id) || id <= 0) throw new Error("Debes indicar un ID valido.")

const connection = await mysql.createConnection({
  host: process.env.DB_HOST ?? "localhost",
  port: Number(process.env.DB_PORT ?? 3306),
  user: process.env.DB_USER ?? "root",
  password: process.env.DB_PASSWORD ?? "",
  database: process.env.DB_NAME ?? "db_inmobiliary_data",
})
const [rows] = await connection.query(
  "SELECT id, barrio, HEX(barrio) AS barrioHex, ciudad, direccion, fuente_id AS fuenteId FROM publicaciones WHERE id = ?",
  [id],
)
await connection.end()
console.log(JSON.stringify(rows, null, 2))
