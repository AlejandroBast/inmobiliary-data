"use client"

import { useEffect, useMemo, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Badge } from "@/components/ui/badge"
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
import { formatCOP } from "@/lib/format"
import type { Fuente } from "@/lib/db/schema"
import { CalendarDays, Eraser, Filter, Home, MapPinned, Ruler, Search, Tags, type LucideIcon } from "lucide-react"

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
  m2Min: string
  m2Max: string
  phTipo: string
}

type PricePreset = {
  label: string
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
  m2Min: "",
  m2Max: "",
  phTipo: "",
}

const pricePresets: PricePreset[] = [
  { label: "Menos de 100M", precioMin: "", precioMax: "100" },
  { label: "100M a 200M", precioMin: "100", precioMax: "200" },
  { label: "200M a 400M", precioMin: "200", precioMax: "400" },
  { label: "Mas de 400M", precioMin: "400", precioMax: "" },
]

const priceSlider = {
  min: 0,
  max: 1000,
  step: 10,
}

function priceInputToMillions(value: string, fallback: number) {
  const clean = value.replace(/\D/g, "")
  if (!clean) return fallback
  const parsed = Number(clean)
  if (!Number.isFinite(parsed)) return fallback
  const millions = parsed > 0 && parsed >= 100000 ? Math.round(parsed / 1_000_000) : parsed
  return Math.min(Math.max(millions, priceSlider.min), priceSlider.max)
}

function formatMillions(value: number) {
  return value >= priceSlider.max ? "Sin limite" : formatCOP(value * 1_000_000)
}

function moneyValue(value: string) {
  const clean = value.replace(/\D/g, "")
  if (!clean) return null
  const parsed = Number(clean)
  if (!Number.isFinite(parsed)) return null
  return parsed > 0 && parsed < 100000 ? parsed * 1_000_000 : parsed
}

function activeCount(values: FiltrosValue) {
  return Object.values(values).filter((value) => {
    const clean = String(value ?? "").trim()
    return clean && clean !== "all"
  }).length
}

export function PublicacionesFiltrosPro({
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

  const totalActive = useMemo(() => activeCount(values), [values])
  const minCOP = moneyValue(values.precioMin)
  const maxCOP = moneyValue(values.precioMax)
  const sliderMin = priceInputToMillions(values.precioMin, priceSlider.min)
  const sliderMax = Math.max(
    sliderMin + priceSlider.step,
    priceInputToMillions(values.precioMax, priceSlider.max),
  )
  const sliderMinPercent = (sliderMin / priceSlider.max) * 100
  const sliderMaxPercent = (Math.min(sliderMax, priceSlider.max) / priceSlider.max) * 100
  const activePreset = pricePresets.find(
    (preset) => preset.precioMin === values.precioMin && preset.precioMax === values.precioMax,
  )

  function setField<K extends keyof FiltrosValue>(key: K, value: FiltrosValue[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function setPricePreset(preset: PricePreset) {
    setValues((current) => ({
      ...current,
      precioMin: preset.precioMin,
      precioMax: preset.precioMax,
    }))
  }

  function setPriceSliderEdge(edge: "min" | "max", rawValue: string) {
    const next = Number(rawValue)
    if (!Number.isFinite(next)) return

    setValues((current) => {
      const currentMin = priceInputToMillions(current.precioMin, priceSlider.min)
      const currentMax = priceInputToMillions(current.precioMax, priceSlider.max)

      if (edge === "min") {
        const nextMin = Math.min(next, currentMax - priceSlider.step)
        return {
          ...current,
          precioMin: nextMin <= priceSlider.min ? "" : String(nextMin),
        }
      }

      const nextMax = Math.max(next, currentMin + priceSlider.step)
      return {
        ...current,
        precioMax: nextMax >= priceSlider.max ? "" : String(nextMax),
      }
    })
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
    <Card className="border-slate-200/70 bg-card/95 dark:border-white/10 dark:bg-zinc-950/70">
      <CardContent className="space-y-5 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                <Filter className="size-4" />
              </span>
              <h2 className="text-base font-semibold tracking-tight">Filtros de busqueda</h2>
            </div>
            <p className="text-sm text-muted-foreground">
              1. Define el segmento, 2. acota precio, 3. aplica para actualizar resultados.
            </p>
          </div>
          <Badge
            variant={totalActive > 0 ? "default" : "outline"}
            className={totalActive > 0 ? "bg-emerald-600 text-white" : ""}
          >
            {totalActive} filtros activos
          </Badge>
        </div>

        <FilterGroup icon={Search} title="1. Datos generales">
          <Field label="ID exacto" htmlFor="filtro-id">
            <Input
              id="filtro-id"
              type="number"
              inputMode="numeric"
              placeholder="Ej. 15"
              value={values.id}
              onChange={(event) => setField("id", event.target.value)}
            />
          </Field>
          <Field label="Tipo de inmueble" htmlFor="filtro-tipo">
            <Input
              id="filtro-tipo"
              list="tipos-inmueble"
              placeholder="Casa, apartamento..."
              value={values.tipoInmueble}
              onChange={(event) => setField("tipoInmueble", event.target.value)}
            />
            <datalist id="tipos-inmueble">
              {["Casa", "Apartamento", "Lote", "Casa lote", "Local", "Oficina", "Finca", "Otro"].map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </Field>
          <Field label="Fuente" htmlFor="filtro-fuente">
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
          </Field>
          <Field label="Propiedad" htmlFor="filtro-ph-tipo">
            <Select value={values.phTipo} onValueChange={(value) => setField("phTipo", value ?? "")}>
              <SelectTrigger id="filtro-ph-tipo">
                <SelectValue placeholder="Todas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="ph">Con PH</SelectItem>
                <SelectItem value="normal">Normales</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </FilterGroup>

        <FilterGroup icon={Home} title="2. Caracteristicas del inmueble">
          <Field label="Habitaciones" htmlFor="filtro-habitaciones">
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
          </Field>
          <Field label="Banos" htmlFor="filtro-banios">
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
          </Field>
          <Field label="Parqueaderos" htmlFor="filtro-parqueadero">
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
          </Field>
        </FilterGroup>

        <FilterGroup icon={MapPinned} title="3. Ubicacion y fecha">
          <Field label="Barrio" htmlFor="filtro-barrio">
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
          </Field>
          <Field label="Fecha de captura" htmlFor="filtro-fecha">
            <div className="relative">
              <CalendarDays className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground" />
              <Input
                id="filtro-fecha"
                type="date"
                value={values.fecha}
                onChange={(event) => setField("fecha", event.target.value)}
                className="pl-8"
              />
            </div>
          </Field>
        </FilterGroup>

        <FilterGroup icon={Ruler} title="4. Metros cuadrados">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Area minima" htmlFor="filtro-m2-min">
              <Input
                id="filtro-m2-min"
                type="number"
                inputMode="decimal"
                min="0"
                placeholder="Ej. 60"
                value={values.m2Min}
                onChange={(event) => setField("m2Min", event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {values.m2Min ? `Desde ${values.m2Min} m2` : "Sin minimo"}
              </p>
            </Field>
            <Field label="Area maxima" htmlFor="filtro-m2-max">
              <Input
                id="filtro-m2-max"
                type="number"
                inputMode="decimal"
                min="0"
                placeholder="Ej. 120"
                value={values.m2Max}
                onChange={(event) => setField("m2Max", event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {values.m2Max ? `Hasta ${values.m2Max} m2` : "Sin maximo"}
              </p>
            </Field>
          </div>
        </FilterGroup>

        <FilterGroup icon={Tags} title="5. Rango de precio">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Precio minimo" htmlFor="filtro-precio-min">
              <Input
                id="filtro-precio-min"
                type="number"
                inputMode="numeric"
                min="0"
                placeholder="Ej. 50"
                value={values.precioMin}
                onChange={(event) => setField("precioMin", event.target.value)}
              />
              <p className="text-xs text-muted-foreground">{minCOP ? formatCOP(minCOP) : "Sin minimo"}</p>
            </Field>
            <Field label="Precio maximo" htmlFor="filtro-precio-max">
              <Input
                id="filtro-precio-max"
                type="number"
                inputMode="numeric"
                min="0"
                placeholder="Ej. 300"
                value={values.precioMax}
                onChange={(event) => setField("precioMax", event.target.value)}
              />
              <p className="text-xs text-muted-foreground">{maxCOP ? formatCOP(maxCOP) : "Sin maximo"}</p>
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            {pricePresets.map((preset) => (
              <Button
                key={preset.label}
                type="button"
                variant={activePreset?.label === preset.label ? "default" : "outline"}
                size="xs"
                onClick={() => setPricePreset(preset)}
                className={activePreset?.label === preset.label ? "bg-emerald-600 text-white hover:bg-emerald-700" : ""}
              >
                {preset.label}
              </Button>
            ))}
          </div>
          <div className="rounded-lg border border-slate-200/70 bg-slate-50/70 p-3 dark:border-white/10 dark:bg-zinc-900/60">
            <div className="mb-2 flex justify-between text-xs text-muted-foreground">
              <span>{formatMillions(sliderMin)}</span>
              <span>{formatMillions(sliderMax)}</span>
            </div>
            <div className="relative h-9">
              <div className="absolute left-0 right-0 top-3 h-2 rounded-full bg-slate-200 dark:bg-white/10" />
              <div
                className="absolute top-3 h-2 rounded-full bg-emerald-500"
                style={{
                  left: `${sliderMinPercent}%`,
                  width: `${Math.max(sliderMaxPercent - sliderMinPercent, 0)}%`,
                }}
              />
              <input
                type="range"
                min={priceSlider.min}
                max={priceSlider.max}
                step={priceSlider.step}
                value={sliderMin}
                aria-label="Precio minimo"
                onChange={(event) => setPriceSliderEdge("min", event.target.value)}
                className="price-range price-range-min absolute inset-x-0 top-0 z-20 h-8 w-full appearance-none bg-transparent"
              />
              <input
                type="range"
                min={priceSlider.min}
                max={priceSlider.max}
                step={priceSlider.step}
                value={sliderMax}
                aria-label="Precio maximo"
                onChange={(event) => setPriceSliderEdge("max", event.target.value)}
                className="price-range price-range-max absolute inset-x-0 top-0 z-30 h-8 w-full appearance-none bg-transparent"
              />
            </div>
          </div>
        </FilterGroup>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button type="button" onClick={applyFilters} className="gap-2 bg-emerald-600 text-white hover:bg-emerald-700">
            <Filter className="size-4" />
            Aplicar filtros
          </Button>
          <Button type="button" variant="outline" onClick={clearFilters} className="gap-2">
            <Eraser className="size-4" />
            Limpiar filtros
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function FilterGroup({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-3 rounded-lg border border-slate-200/70 bg-slate-50/70 p-3 dark:border-white/10 dark:bg-zinc-900/60">
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-emerald-600 dark:text-emerald-300" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="grid gap-3">{children}</div>
    </section>
  )
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}
