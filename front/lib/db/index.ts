import { drizzle } from "drizzle-orm/mysql2"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import mysql from "mysql2/promise"
import * as schema from "./schema"

function loadRootEnv() {
	const rootEnvPath = join(process.cwd(), "..", ".env")
	if (!existsSync(rootEnvPath)) return

	for (const line of readFileSync(rootEnvPath, "utf8").split(/\r?\n/)) {
		const trimmed = line.trim()
		if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue

		const [key, ...valueParts] = trimmed.split("=")
		process.env[key] ??= valueParts.join("=")
	}
}

loadRootEnv()

const pool = mysql.createPool({
	host: process.env.DB_HOST ?? "localhost",
	port: Number(process.env.DB_PORT ?? "3306"),
	user: process.env.DB_USER ?? "root",
	password: process.env.DB_PASSWORD ?? "",
	database: process.env.DB_NAME ?? "db_inmobiliary_data",
	waitForConnections: true,
	connectionLimit: 10,
})

export { pool }
export const db = drizzle(pool, { schema, mode: "default" })
