"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Fuente } from "@/lib/db/schema"
import { ChevronDown, Eraser, Filter, X } from "lucide-react"

type ColumnFilters = {
  id: string; tipoInmueble: string; fuenteId: string; fecha: string
  habitaciones: string; banios: string; parqueadero: string; barrio: string
  precioMin: string; precioMax: string; m2Min: string; m2Max: string
  phTipo: string; duplicados: string
}
type FilterGroup = "id" | "publicacion" | "ubicacion" | "fuente" | "precio" | "area" | "caracteristicas" | "fecha"

const filterKeys: Array<keyof ColumnFilters> = [
  "id", "tipoInmueble", "fuenteId", "fecha", "habitaciones", "banios", "parqueadero",
  "barrio", "precioMin", "precioMax", "m2Min", "m2Max", "phTipo", "duplicados",
]
const groupKeys: Record<FilterGroup, Array<keyof ColumnFilters>> = {
  id: ["id"], publicacion: ["tipoInmueble", "phTipo", "duplicados"], ubicacion: ["barrio"],
  fuente: ["fuenteId"], precio: ["precioMin", "precioMax"], area: ["m2Min", "m2Max"],
  caracteristicas: ["habitaciones", "banios", "parqueadero"], fecha: ["fecha"],
}
const emptyFilters = Object.fromEntries(filterKeys.map((key) => [key, ""])) as ColumnFilters
const selectClass = "h-9 min-w-[150px] rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
const inputClass = "h-9 min-w-[150px] text-sm"

function valuesFromParams(params: URLSearchParams): ColumnFilters {
  return Object.fromEntries(filterKeys.map((key) => [key, params.get(key) ?? ""])) as ColumnFilters
}

export function PublicacionesColumnFilters({ fuentes, barrios, hasSinBarrio }: {
  fuentes: Fuente[]; barrios: Array<{ value: string; label: string }>; hasSinBarrio: boolean
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const paramsSnapshot = searchParams.toString()
  const [values, setValues] = useState(() => valuesFromParams(new URLSearchParams(paramsSnapshot)))
  const [openGroup, setOpenGroup] = useState<FilterGroup | null>(null)

  useEffect(() => setValues(valuesFromParams(new URLSearchParams(paramsSnapshot))), [paramsSnapshot])
  const setField = (key: keyof ColumnFilters, value: string) => setValues((current) => ({ ...current, [key]: value }))
  const groupActive = (group: FilterGroup) => groupKeys[group].some((key) => values[key].trim() && values[key] !== "all")

  function applyFilters() {
    const params = new URLSearchParams(paramsSnapshot)
    params.delete("ubicacion")
    filterKeys.forEach((key) => {
      const value = values[key].trim()
      if (value && value !== "all") params.set(key, value); else params.delete(key)
    })
    setOpenGroup(null)
    router.push(params.toString() ? `${pathname}?${params}` : pathname)
  }

  function clearFilters() {
    setValues(emptyFilters)
    const params = new URLSearchParams(paramsSnapshot)
    params.delete("ubicacion")
    filterKeys.forEach((key) => params.delete(key))
    setOpenGroup(null)
    router.push(params.toString() ? `${pathname}?${params}` : pathname)
  }

  function button(group: FilterGroup, label: string) {
    const active = groupActive(group)
    return (
      <button type="button" onClick={() => setOpenGroup((current) => current === group ? null : group)}
        className={`mx-auto flex h-7 items-center gap-1 rounded-md px-2 text-[11px] font-medium transition ${active ? "bg-emerald-600 text-white" : "text-muted-foreground hover:bg-emerald-100 hover:text-emerald-800 dark:hover:bg-emerald-900/40"}`}>
        <Filter className="size-3" />{label}<ChevronDown className={`size-3 transition ${openGroup === group ? "rotate-180" : ""}`} />
      </button>
    )
  }

  const numericOptions = (label: string, parking = false) => <>
    <option value="">{label}</option>{parking && <option value="0">Ninguno</option>}
    <option value="1">1</option><option value="2">2</option><option value="3">3</option>
    <option value={parking ? "3+" : "4+"}>{parking ? "3 o mas" : "4 o mas"}</option>
  </>

  return <>
    <tr className="border-b bg-slate-50/80 dark:bg-zinc-900/80">
      <th className="p-1">{button("id", "Filtrar")}</th>
      <th className="p-1">{button("publicacion", "Filtrar")}</th>
      <th className="p-1">{button("ubicacion", "Filtrar")}</th>
      <th className="p-1">{button("fuente", "Filtrar")}</th>
      <th className="p-1">{button("precio", "Filtrar")}</th>
      <th className="p-1">{button("area", "Filtrar")}</th>
      <th className="p-1 text-center text-[10px] font-normal text-muted-foreground">Calculado</th>
      <th className="p-1">{button("caracteristicas", "Filtrar")}</th>
      <th className="p-1 text-center text-[10px] font-normal text-muted-foreground">Sin filtro</th>
      <th className="p-1">{button("fecha", "Filtrar")}</th>
      <th className="p-1"><Button type="button" variant="ghost" size="sm" onClick={clearFilters} className="h-7 gap-1 px-2 text-[11px]"><Eraser className="size-3" />Limpiar</Button></th>
    </tr>
    {openGroup && (
      <tr className="border-b border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/30">
        <th colSpan={11} className="p-3">
          <div className="flex flex-wrap items-center gap-2 text-left font-normal">
            {openGroup === "id" && <Input type="number" placeholder="ID exacto" value={values.id} onChange={(e) => setField("id", e.target.value)} className={inputClass} />}
            {openGroup === "publicacion" && <>
              <Input placeholder="Tipo de inmueble" value={values.tipoInmueble} onChange={(e) => setField("tipoInmueble", e.target.value)} className={inputClass} />
              <select value={values.phTipo} onChange={(e) => setField("phTipo", e.target.value)} className={selectClass}><option value="">Todo PH</option><option value="ph">Con PH</option><option value="normal">Sin PH</option></select>
              <select value={values.duplicados} onChange={(e) => setField("duplicados", e.target.value)} className={selectClass}><option value="">Todas</option><option value="con">Repetidas</option><option value="sin">No repetidas</option></select>
            </>}
            {openGroup === "ubicacion" && <select value={values.barrio} onChange={(e) => setField("barrio", e.target.value)} className={selectClass}><option value="">Todos los barrios</option>{hasSinBarrio && <option value="__sin_barrio">Sin barrio</option>}{barrios.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>}
            {openGroup === "fuente" && <select value={values.fuenteId} onChange={(e) => setField("fuenteId", e.target.value)} className={selectClass}><option value="">Todas las fuentes</option>{fuentes.map((item) => <option key={item.id} value={String(item.id)}>{item.nombre}</option>)}</select>}
            {openGroup === "precio" && <><Input type="number" placeholder="Precio minimo (millones)" value={values.precioMin} onChange={(e) => setField("precioMin", e.target.value)} className={inputClass} /><Input type="number" placeholder="Precio maximo (millones)" value={values.precioMax} onChange={(e) => setField("precioMax", e.target.value)} className={inputClass} /></>}
            {openGroup === "area" && <><Input type="number" placeholder="Area minima m2" value={values.m2Min} onChange={(e) => setField("m2Min", e.target.value)} className={inputClass} /><Input type="number" placeholder="Area maxima m2" value={values.m2Max} onChange={(e) => setField("m2Max", e.target.value)} className={inputClass} /></>}
            {openGroup === "caracteristicas" && <><select value={values.habitaciones} onChange={(e) => setField("habitaciones", e.target.value)} className={selectClass}>{numericOptions("Habitaciones")}</select><select value={values.banios} onChange={(e) => setField("banios", e.target.value)} className={selectClass}>{numericOptions("Banos")}</select><select value={values.parqueadero} onChange={(e) => setField("parqueadero", e.target.value)} className={selectClass}>{numericOptions("Parqueaderos", true)}</select></>}
            {openGroup === "fecha" && <Input type="date" value={values.fecha} onChange={(e) => setField("fecha", e.target.value)} className={inputClass} />}
            <div className="ml-auto flex gap-2">
              <Button type="button" size="sm" onClick={applyFilters} className="gap-1 bg-emerald-600 hover:bg-emerald-700"><Filter className="size-4" />Aplicar</Button>
              <Button type="button" size="icon" variant="ghost" onClick={() => setOpenGroup(null)} aria-label="Cerrar filtros"><X className="size-4" /></Button>
            </div>
          </div>
        </th>
      </tr>
    )}
  </>
}
