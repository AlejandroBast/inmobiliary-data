import { drizzle } from "drizzle-orm/mysql2"
import mysql from "mysql2/promise"
import * as schema from "./schema"

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
