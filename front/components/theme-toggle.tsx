"use client"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const currentTheme = mounted ? resolvedTheme : "light"

  return (
    <div className="inline-flex rounded-lg border bg-background p-1" aria-label="Cambiar tema">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setTheme("light")}
        aria-pressed={currentTheme === "light"}
        className={cn(
          "gap-1.5",
          currentTheme === "light" && "bg-muted text-foreground hover:bg-muted",
        )}
      >
        <Sun className="size-4" />
        Claro
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setTheme("dark")}
        aria-pressed={currentTheme === "dark"}
        className={cn(
          "gap-1.5",
          currentTheme === "dark" && "bg-muted text-foreground hover:bg-muted",
        )}
      >
        <Moon className="size-4" />
        Oscuro
      </Button>
    </div>
  )
}
