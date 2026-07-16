"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Fuente } from "@/lib/db/schema"
import { Eraser, Filter } from "lucide-react"

type ColumnFilters = {
  id: string
  tipoInmueble: string
  fuenteId: string
  fecha: string
  habitaciones: string
  banios: string
  parqueadero: string
  barrio: string
  precioMin: string
  precioMax: string
  m2Min: string
  m2Max: string
  phTipo: string
  duplicados: string
}

const filterKeys: Array<keyof ColumnFilters> = [
  "id", "tipoInmueble", "fuenteId", "fecha", "habitaciones", "banios",
  "parqueadero", "barrio", "precioMin", "precioMax", "m2Min", "m2Max",
  "phTipo", "duplicados",
]

const emptyFilters: ColumnFilters = Object.fromEntries(filterKeys.map((key) => [key, ""])) as ColumnFilters

const selectClass = "h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
const inputClass = "h-8 min-w-[74px] px-2 text-xs"

function valuesFromParams(params: URLSearchParams): ColumnFilters {
  return Object.fromEntries(filterKeys.map((key) => [key, params.get(key) ?? ""])) as ColumnFilters
}

export function PublicacionesColumnFilters({
  fuentes,
  barrios,
  hasSinBarrio,
}: {
  fuentes: Fuente[]
  barrios: Array<{ value: string; label: string }>
  hasSinBarrio: boolean
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const paramsSnapshot = searchParams.toString()
  const [values, setValues] = useState<ColumnFilters>(() => valuesFromParams(new URLSearchParams(paramsSnapshot)))

  useEffect(() => {
    setValues(valuesFromParams(new URLSearchParams(paramsSnapshot)))
  }, [paramsSnapshot])

  function setField(key: keyof ColumnFilters, value: string) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function applyFilters() {
    const params = new URLSearchParams(paramsSnapshot)
    params.delete("ubicacion")
    filterKeys.forEach((key) => {
      const value = values[key].trim()
      if (value && value !== "all") params.set(key, value)
      else params.delete(key)
    })
    router.push(params.toString() ? `${pathname}?${params}` : pathname)
  }

  function clearFilters() {
    setValues(emptyFilters)
    const params = new URLSearchParams(paramsSnapshot)
    params.delete("ubicacion")
    filterKeys.forEach((key) => params.delete(key))
    router.push(params.toString() ? `${pathname}?${params}` : pathname)
  }

  function submitOnEnter(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") applyFilters()
  }

  return (
    <tr className="border-b bg-emerald-50/70 align-top dark:bg-emerald-950/20">
      <th className="p-2">
        <Input aria-label="Filtrar por ID" type="number" placeholder="ID" value={values.id} onChange={(e) => setField("id", e.target.value)} onKeyDown={submitOnEnter} className={inputClass} />
      </th>
      <th className="min-w-[180px] space-y-1 p-2">
        <Input aria-label="Filtrar por tipo de inmueble" placeholder="Tipo de inmueble" value={values.tipoInmueble} onChange={(e) => setField("tipoInmueble", e.target.value)} onKeyDown={submitOnEnter} className={inputClass} />
        <div className="grid grid-cols-2 gap-1">
          <select aria-label="Filtrar por propiedad horizontal" value={values.phTipo} onChange={(e) => setField("phTipo", e.target.value)} className={selectClass}>
            <option value="">Todo PH</option><option value="ph">Con PH</option><option value="normal">Sin PH</option>
          </select>
          <select aria-label="Filtrar publicaciones repetidas" value={values.duplicados} onChange={(e) => setField("duplicados", e.target.value)} className={selectClass}>
            <option value="">Todas</option><option value="con">Repetidas</option><option value="sin">No repetidas</option>
          </select>
        </div>
      </th>
      <th className="min-w-[150px] p-2">
        <select aria-label="Filtrar por barrio" value={values.barrio} onChange={(e) => setField("barrio", e.target.value)} className={selectClass}>
          <option value="">Todos los barrios</option>
          {hasSinBarrio && <option value="__sin_barrio">Sin barrio</option>}
          {barrios.map((barrio) => <option key={barrio.value} value={barrio.value}>{barrio.label}</option>)}
        </select>
      </th>
      <th className="min-w-[140px] p-2">
        <select aria-label="Filtrar por fuente" value={values.fuenteId} onChange={(e) => setField("fuenteId", e.target.value)} className={selectClass}>
          <option value="">Todas las fuentes</option>
          {fuentes.map((fuente) => <option key={fuente.id} value={String(fuente.id)}>{fuente.nombre}</option>)}
        </select>
      </th>
      <th className="min-w-[120px] space-y-1 p-2">
        <Input aria-label="Precio minimo" type="number" placeholder="Min. millones" value={values.precioMin} onChange={(e) => setField("precioMin", e.target.value)} onKeyDown={submitOnEnter} className={inputClass} />
        <Input aria-label="Precio maximo" type="number" placeholder="Max. millones" value={values.precioMax} onChange={(e) => setField("precioMax", e.target.value)} onKeyDown={submitOnEnter} className={inputClass} />
      </th>
      <th className="min-w-[105px] space-y-1 p-2">
        <Input aria-label="Area minima" type="number" placeholder="Min. m2" value={values.m2Min} onChange={(e) => setField("m2Min", e.target.value)} onKeyDown={submitOnEnter} className={inputClass} />
        <Input aria-label="Area maxima" type="number" placeholder="Max. m2" value={values.m2Max} onChange={(e) => setField("m2Max", e.target.value)} onKeyDown={submitOnEnter} className={inputClass} />
      </th>
      <th className="p-2 text-center text-xs font-normal text-muted-foreground">Se calcula<br />con precio y area</th>
      <th className="min-w-[125px] space-y-1 p-2">
        {(["habitaciones", "banios", "parqueadero"] as const).map((key) => (
          <select key={key} aria-label={`Filtrar por ${key}`} value={values[key]} onChange={(e) => setField(key, e.target.value)} className={selectClass}>
            <option value="">{key === "habitaciones" ? "Habitaciones" : key === "banios" ? "Banos" : "Parqueaderos"}</option>
            {key === "parqueadero" && <option value="0">Ninguno</option>}
            <option value="1">1</option><option value="2">2</option><option value="3">3</option>
            <option value={key === "parqueadero" ? "3+" : "4+"}>{key === "parqueadero" ? "3 o mas" : "4 o mas"}</option>
          </select>
        ))}
      </th>
      <th className="p-2 text-center text-xs font-normal text-muted-foreground">Sin filtro</th>
      <th className="min-w-[145px] p-2">
        <Input aria-label="Filtrar por fecha de captura" type="date" value={values.fecha} onChange={(e) => setField("fecha", e.target.value)} onKeyDown={submitOnEnter} className={inputClass} />
      </th>
      <th className="min-w-[112px] space-y-1 p-2">
        <Button type="button" size="sm" onClick={applyFilters} className="h-8 w-full gap-1 bg-emerald-600 px-2 text-xs hover:bg-emerald-700"><Filter className="size-3" />Aplicar</Button>
        <Button type="button" size="sm" variant="outline" onClick={clearFilters} className="h-8 w-full gap-1 px-2 text-xs"><Eraser className="size-3" />Limpiar</Button>
      </th>
    </tr>
  )
}
