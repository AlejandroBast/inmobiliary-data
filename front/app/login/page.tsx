import { LoginForm } from "@/components/login-form"

export const dynamic = "force-dynamic"

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>
}) {
  const { from } = await searchParams

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <LoginForm from={from ?? "/"} />
    </div>
  )
}
