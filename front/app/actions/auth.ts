"use server"

import { cookies } from "next/headers"
import { redirect } from "next/navigation"

const SESSION_COOKIE = "auth_session"
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30 // 30 dias

export async function login(_prevState: { error: string } | null, formData: FormData) {
  const username = String(formData.get("username") ?? "").trim()
  const password = String(formData.get("password") ?? "")
  const from = String(formData.get("from") ?? "/")

  const expectedUsername = process.env.AUTH_USERNAME
  const expectedPassword = process.env.AUTH_PASSWORD
  const secret = process.env.AUTH_SESSION_SECRET

  if (!expectedUsername || !expectedPassword || !secret) {
    return { error: "Falta configurar AUTH_USERNAME/AUTH_PASSWORD/AUTH_SESSION_SECRET en .env.local" }
  }

  if (username !== expectedUsername || password !== expectedPassword) {
    return { error: "Usuario o contraseña incorrectos." }
  }

  const cookieStore = await cookies()
  cookieStore.set(SESSION_COOKIE, secret, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  })

  redirect(from.startsWith("/") ? from : "/")
}

export async function logout() {
  const cookieStore = await cookies()
  cookieStore.delete(SESSION_COOKIE)
  redirect("/login")
}
