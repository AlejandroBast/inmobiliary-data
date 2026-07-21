import { Skeleton } from "@/components/ui/skeleton"

export default function Loading() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-20 w-full max-w-[1760px] items-center gap-3 px-4 py-3 lg:px-6">
        <Skeleton className="size-12 rounded-2xl" />
        <div className="space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-3 w-72" />
        </div>
      </div>
      <main className="mx-auto w-full max-w-[1760px] space-y-4 px-4 py-6 lg:px-6">
        <Skeleton className="h-48 w-full rounded-2xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
        <Skeleton className="h-96 w-full rounded-2xl" />
      </main>
    </div>
  )
}
