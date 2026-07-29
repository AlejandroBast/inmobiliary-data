import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

const SESSION_COOKIE = "auth_session"
const PUBLIC_PATHS = new Set(["/login"])

function isPublicAsset(pathname: string) {
  return (
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico" ||
    /^\/icon-(light|dark)-32x32\.png$/.test(pathname) ||
    /\.(png|jpg|jpeg|svg|webp|gif|ico)$/i.test(pathname)
  )
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (PUBLIC_PATHS.has(pathname) || isPublicAsset(pathname)) {
    return NextResponse.next()
  }

  const expected = process.env.AUTH_SESSION_SECRET
  const token = request.cookies.get(SESSION_COOKIE)?.value

  if (expected && token === expected) {
    return NextResponse.next()
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "No autenticado" }, { status: 401 })
  }

  const loginUrl = new URL("/login", request.url)
  loginUrl.searchParams.set("from", pathname)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
}
