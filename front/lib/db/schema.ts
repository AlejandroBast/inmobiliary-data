import {
  bigint,
  boolean,
  decimal,
  json,
  int,
  mysqlTable,
  text,
  timestamp,
  varchar,
} from "drizzle-orm/mysql-core"

export const fuentesInmobiliarias = mysqlTable("fuentes_inmobiliarias", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  nombre: varchar("nombre", { length: 100 }).notNull().unique(),
  urlBase: text("url_base"),
  tipoFuente: varchar("tipo_fuente", { length: 50 }),
  activa: boolean("activa").default(true),
  descripcion: text("descripcion"),
})

export const barrios = mysqlTable("barrios", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  nombre: varchar("nombre", { length: 150 }).notNull(),
  nombreNormalizado: varchar("nombre_normalizado", { length: 150 }).notNull(),
  activo: boolean("activo").notNull().default(true),
  fechaCreacion: timestamp("fecha_creacion").notNull().defaultNow(),
})

export const tiposInmueble = mysqlTable("tipos_inmueble", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  nombre: varchar("nombre", { length: 80 }).notNull(),
  nombreNormalizado: varchar("nombre_normalizado", { length: 80 }).notNull(),
  activo: boolean("activo").notNull().default(true),
  fechaCreacion: timestamp("fecha_creacion").notNull().defaultNow(),
})

export const publicaciones = mysqlTable("publicaciones", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  fuenteId: bigint("fuente_id", { mode: "number" }).notNull(),
  codigoExterno: varchar("codigo_externo", { length: 100 }),
  linkOrigen: text("link_origen").notNull().unique(),
  linksAdicionales: json("links_adicionales"),
  fechaCaptura: timestamp("fecha_captura").notNull().defaultNow(),
  coordenadas: text("coordenadas"),
  latitud: decimal("latitud", { precision: 10, scale: 7 }),
  longitud: decimal("longitud", { precision: 10, scale: 7 }),
  direccion: text("direccion"),
  ciudad: varchar("ciudad", { length: 100 }).default("Pasto"),
  barrio: varchar("barrio", { length: 150 }),
  tipoInmueble: varchar("tipo_inmueble", { length: 80 }),
  ph: text("ph"),
  estrato: int("estrato"),
  descripcion: text("descripcion"),
  precio: decimal("precio", { precision: 15, scale: 0 }).notNull(),
  m2: decimal("m2", { precision: 10, scale: 2 }),
  precioM2: decimal("precio_m2", { precision: 15, scale: 0 }),
  m2Construido: decimal("m2_construido", { precision: 10, scale: 2 }),
  precioM2Construido: decimal("precio_m2_construido", { precision: 15, scale: 0 }),
  antiguedad: varchar("antiguedad", { length: 100 }),
  pisos: int("pisos"),
  habitaciones: int("habitaciones"),
  banios: int("banios"),
  parqueadero: int("parqueadero"),
  administracion: decimal("administracion", { precision: 15, scale: 0 }),
  notas: text("notas"),
})

export type Publicacion = typeof publicaciones.$inferSelect
export type Fuente = typeof fuentesInmobiliarias.$inferSelect
export type Barrio = typeof barrios.$inferSelect
export type TipoInmueble = typeof tiposInmueble.$inferSelect
