"use client"

import { useActionState } from "react"
import { Building2, Lock, User } from "lucide-react"
import { login } from "@/app/actions/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function LoginForm({ from }: { from: string }) {
  const [state, formAction, isPending] = useActionState(login, null)

  return (
    <Card className="w-full max-w-sm shadow-lg">
      <CardHeader className="items-center gap-2 text-center">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary/70 text-primary-foreground shadow-md shadow-primary/20 ring-1 ring-primary/30">
          <Building2 className="size-6" />
        </div>
        <h1 className="text-xl font-bold tracking-tight">Publicaciones Inmobiliarias</h1>
        <p className="text-sm text-muted-foreground">Iniciá sesión para continuar</p>
      </CardHeader>
      <CardContent>
        <form action={formAction} className="space-y-4">
          <input type="hidden" name="from" value={from} />
          <div className="space-y-1.5">
            <Label htmlFor="username">Usuario</Label>
            <div className="relative">
              <User className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input id="username" name="username" autoComplete="username" required autoFocus className="pl-9" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Contraseña</Label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input id="password" name="password" type="password" autoComplete="current-password" required className="pl-9" />
            </div>
          </div>
          {state?.error && <p className="text-sm text-destructive">{state.error}</p>}
          <Button type="submit" className="w-full" disabled={isPending}>
            {isPending ? "Ingresando..." : "Ingresar"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
