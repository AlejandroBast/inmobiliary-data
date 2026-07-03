export function formatCOP(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—"
  const num = typeof value === "string" ? Number(value) : value
  if (Number.isNaN(num)) return "—"
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(num)
}

export function formatNumber(value: string | number | null | undefined, suffix = "") {
  if (value === null || value === undefined || value === "") return "—"
  const num = typeof value === "string" ? Number(value) : value
  if (Number.isNaN(num)) return "—"
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(num)}${suffix}`
}

export function formatDate(value: string | Date | null | undefined) {
  if (!value) return "—"
  const date = typeof value === "string" ? new Date(value) : value
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date)
}
