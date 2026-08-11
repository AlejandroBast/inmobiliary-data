import {
  bigint,
  boolean,
  decimal,
  json,
  int,
  mysqlEnum,
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

export const phConjuntos = mysqlTable("ph_conjuntos", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  nombre: varchar("nombre", { length: 150 }).notNull(),
  nombreNormalizado: varchar("nombre_normalizado", { length: 150 }).notNull(),
  activo: boolean("activo").notNull().default(true),
  fechaCreacion: timestamp("fecha_creacion").notNull().defaultNow(),
})

export const publicaciones = mysqlTable("publicaciones", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  // Opcional desde la migracion 005: en la carga manual no siempre hay un portal
  // detras. La clave foranea sigue: si se indica una, tiene que existir.
  fuenteId: bigint("fuente_id", { mode: "number" }),
  codigoExterno: varchar("codigo_externo", { length: 100 }),
  // Opcionales desde la migracion 004: en la carga manual el cliente anota
  // inmuebles que vio en cualquier lado, sin link publicado ni precio cerrado.
  linkOrigen: text("link_origen").unique(),
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
  precio: decimal("precio", { precision: 15, scale: 0 }),
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
  // Cache liviano de la nota mas reciente (la usa la columna "Nota" del
  // listado); el historial completo vive en publicacion_notas.
  notas: text("notas"),
  fechaNota: timestamp("fecha_nota"),
})

// Historial de notas por publicacion (migracion 008): cada "Agregar nota" es
// una fila propia en vez de pisar la anterior.
export const publicacionNotas = mysqlTable("publicacion_notas", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  publicacionId: bigint("publicacion_id", { mode: "number" }).notNull(),
  contenido: text("contenido").notNull(),
  fechaCreacion: timestamp("fecha_creacion").notNull().defaultNow(),
})

// Comentarios escritos en la comparacion de duplicados y motivo de cada
// eliminacion (migracion 009). Ojo con la diferencia contra publicacionNotas:
// aca publicacionId NO es una clave foranea. La tabla existe para justificar
// por que se borro un inmueble, asi que sus filas tienen que sobrevivir a ese
// borrado; los snapshot* guardan como se veia la publicacion al comentarla,
// que es lo unico que queda de ella despues.
export const comentariosComparacion = mysqlTable("comentarios_comparacion", {
  id: bigint("id", { mode: "number" }).primaryKey().autoincrement(),
  publicacionId: bigint("publicacion_id", { mode: "number" }).notNull(),
  publicacionRaizId: bigint("publicacion_raiz_id", { mode: "number" }),
  tipo: mysqlEnum("tipo", ["comentario", "eliminacion"]).notNull().default("comentario"),
  contenido: text("contenido").notNull(),
  snapshotTipoInmueble: varchar("snapshot_tipo_inmueble", { length: 80 }),
  snapshotBarrio: varchar("snapshot_barrio", { length: 150 }),
  snapshotFuente: varchar("snapshot_fuente", { length: 100 }),
  snapshotPrecio: decimal("snapshot_precio", { precision: 15, scale: 0 }),
  snapshotLink: text("snapshot_link"),
  fechaCreacion: timestamp("fecha_creacion").notNull().defaultNow(),
})

export type Publicacion = typeof publicaciones.$inferSelect
export type Fuente = typeof fuentesInmobiliarias.$inferSelect
export type Barrio = typeof barrios.$inferSelect
export type TipoInmueble = typeof tiposInmueble.$inferSelect
export type PhConjunto = typeof phConjuntos.$inferSelect
export type PublicacionNota = typeof publicacionNotas.$inferSelect
export type ComentarioComparacion = typeof comentariosComparacion.$inferSelect
