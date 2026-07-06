import { ThemeToggle } from "@/components/theme-toggle"
import type { ReactNode } from "react"

type AppShellProps = {
  active: "dashboard" | "publicaciones"
  title: string
  subtitle: string
  icon: ReactNode
  actions?: ReactNode
  children: ReactNode
}

export function AppShell({ title, subtitle, icon, actions, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b bg-background/92 backdrop-blur">
        <div className="flex min-h-16 flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between lg:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              {icon}
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold tracking-tight">{title}</h1>
              <p className="text-sm text-muted-foreground">{subtitle}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1760px] space-y-6 px-4 py-5 lg:px-6">
        {children}
      </main>
    </div>
  )
}
