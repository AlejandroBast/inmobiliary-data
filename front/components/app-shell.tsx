import { ThemeToggle } from "@/components/theme-toggle"
import { Badge } from "@/components/ui/badge"
import type { ReactNode } from "react"

type AppShellProps = {
  active: "dashboard" | "publicaciones"
  title: string
  subtitle: string
  icon: ReactNode
  actions?: ReactNode
  children: ReactNode
}

const activeLabel: Record<AppShellProps["active"], string> = {
  dashboard: "Dashboard",
  publicaciones: "Publicaciones",
}

export function AppShell({ active, title, subtitle, icon, actions, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-72 bg-[radial-gradient(60%_100%_at_50%_0%,color-mix(in_oklch,var(--primary)_10%,transparent),transparent)]"
      />
      <header className="sticky top-0 z-30 border-b border-border/70 bg-background/85 backdrop-blur-md supports-backdrop-filter:bg-background/70">
        <div className="mx-auto flex min-h-20 w-full max-w-[1760px] flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between lg:px-6">
          <div className="flex min-w-0 items-center gap-3.5">
            <div className="relative flex size-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary/70 text-primary-foreground shadow-md shadow-primary/20 ring-1 ring-primary/30">
              {icon}
            </div>
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="truncate text-2xl font-bold tracking-tight">{title}</h1>
                <Badge variant="outline" className="tone-primary hidden sm:inline-flex">
                  {activeLabel[active]}
                </Badge>
              </div>
              <p className="truncate text-sm text-muted-foreground">{subtitle}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            <ThemeToggle />
          </div>
        </div>
        <div className="header-accent-bar h-[2px] w-full" aria-hidden />
      </header>

      <main className="mx-auto w-full max-w-[1760px] space-y-6 px-4 py-6 lg:px-6">
        {children}
      </main>
    </div>
  )
}
