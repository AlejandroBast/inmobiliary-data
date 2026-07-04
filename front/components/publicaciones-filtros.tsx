"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { Fuente } from "@/lib/db/schema"

type FiltrosValue = {
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
}

const initialFilters: FiltrosValue = {
  id: "",
  tipoInmueble: "",
  fuenteId: "",
  fecha: "",
  habitaciones: "",
  banios: "",
  parqueadero: "",
  barrio: "",
  precioMin: "",
  precioMax: "",
}

export function PublicacionesFiltros({
  fuentes,
  barrios,
  hasSinBarrio,
  initialValues,
}: {
  fuentes: Fuente[]
  barrios: Array<{ value: string; label: string }>
  hasSinBarrio: boolean
  initialValues: Partial<FiltrosValue>
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [values, setValues] = useState<FiltrosValue>({
    ...initialFilters,
    ...initialValues,
  })

  useEffect(() => {
    setValues({
      ...initialFilters,
      ...initialValues,
    })
  }, [initialValues])

  function setField<K extends keyof FiltrosValue>(key: K, value: FiltrosValue[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function applyFilters() {
    const params = new URLSearchParams(searchParams.toString())

    params.delete("ubicacion")

    Object.entries(values).forEach(([key, value]) => {
      const cleanValue = String(value || "").trim()
      if (cleanValue && cleanValue !== "all") {
        params.set(key, cleanValue)
      } else {
        params.delete(key)
      }
    })

    router.push(params.toString() ? `${pathname}?${params.toString()}` : pathname)
  }

  function clearFilters() {
    setValues(initialFilters)
    router.push(pathname)
  }

  return (
    <Card className="border-dashed">
      <CardContent className="space-y-4 pt-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Filtros de busqueda</h2>
          <p className="text-sm text-muted-foreground">
            Combina varios filtros y aplica solo los que necesites.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-2">
            <Label htmlFor="filtro-id">ID exacto</Label>
            <Input
              id="filtro-id"
              type="number"
              inputMode="numeric"
              placeholder="Ej. 15"
              value={values.id}
              onChange={(event) => setField("id", event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-tipo">Tipo de inmueble</Label>
            <Input
              id="filtro-tipo"
              list="tipos-inmueble"
              placeholder="Casa, Apartamento, Lote..."
              value={values.tipoInmueble}
              onChange={(event) => setField("tipoInmueble", event.target.value)}
            />
            <datalist id="tipos-inmueble">
              {["Casa", "Apartamento", "Lote", "Casa lote", "Local", "Oficina", "Finca", "Otro"].map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-fuente">Fuente</Label>
            <Select value={values.fuenteId} onValueChange={(value) => setField("fuenteId", value ?? "")}>
              <SelectTrigger id="filtro-fuente">
                <SelectValue placeholder="Todas las fuentes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas las fuentes</SelectItem>
                {fuentes.map((fuente) => (
                  <SelectItem key={fuente.id} value={String(fuente.id)}>
                    {fuente.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-fecha">Fecha de captura</Label>
            <Input
              id="filtro-fecha"
              type="date"
              value={values.fecha}
              onChange={(event) => setField("fecha", event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-habitaciones">Habitaciones</Label>
            <Select value={values.habitaciones} onValueChange={(value) => setField("habitaciones", value ?? "")}>
              <SelectTrigger id="filtro-habitaciones">
                <SelectValue placeholder="Cualquiera" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Cualquiera</SelectItem>
                <SelectItem value="1">1</SelectItem>
                <SelectItem value="2">2</SelectItem>
                <SelectItem value="3">3</SelectItem>
                <SelectItem value="4+">4 o mas</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-banios">Banos</Label>
            <Select value={values.banios} onValueChange={(value) => setField("banios", value ?? "")}>
              <SelectTrigger id="filtro-banios">
                <SelectValue placeholder="Cualquiera" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Cualquiera</SelectItem>
                <SelectItem value="1">1</SelectItem>
                <SelectItem value="2">2</SelectItem>
                <SelectItem value="3">3</SelectItem>
                <SelectItem value="4+">4 o mas</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-parqueadero">Parqueaderos</Label>
            <Select value={values.parqueadero} onValueChange={(value) => setField("parqueadero", value ?? "")}>
              <SelectTrigger id="filtro-parqueadero">
                <SelectValue placeholder="Cualquiera" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Cualquiera</SelectItem>
                <SelectItem value="0">Sin parqueadero</SelectItem>
                <SelectItem value="1">1</SelectItem>
                <SelectItem value="2">2</SelectItem>
                <SelectItem value="3+">3 o mas</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-barrio">Barrio</Label>
            <Select value={values.barrio} onValueChange={(value) => setField("barrio", value ?? "")}>
              <SelectTrigger id="filtro-barrio">
                <SelectValue placeholder="Todos los barrios" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos los barrios</SelectItem>
                {hasSinBarrio && <SelectItem value="__sin_barrio">Sin barrio</SelectItem>}
                {barrios.map((barrio) => (
                  <SelectItem key={barrio.value} value={barrio.value}>
                    {barrio.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-precio-min">Precio minimo</Label>
            <Input
              id="filtro-precio-min"
              type="number"
              inputMode="numeric"
              min="0"
              placeholder="Ej. 50"
              value={values.precioMin}
              onChange={(event) => setField("precioMin", event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="filtro-precio-max">Precio maximo</Label>
            <Input
              id="filtro-precio-max"
              type="number"
              inputMode="numeric"
              min="0"
              placeholder="Ej. 300"
              value={values.precioMax}
              onChange={(event) => setField("precioMax", event.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button type="button" onClick={applyFilters} className="gap-2">
            Aplicar filtros
          </Button>
          <Button type="button" variant="outline" onClick={clearFilters}>
            Limpiar filtros
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
