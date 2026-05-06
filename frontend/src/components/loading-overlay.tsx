"use client"

import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

type Props = {
  open: boolean
  title?: string
  message?: string
  progressPct?: number | null
  details?: string[]
  scope?: "page" | "section"
  className?: string
}

function LoadingOverlay({
  open,
  title = "Cargando",
  message,
  progressPct,
  details,
  scope = "section",
  className,
}: Props) {
  if (!open) return null

  const normalizedProgress =
    typeof progressPct === "number" && Number.isFinite(progressPct) ? Math.max(0, Math.min(100, progressPct)) : null

  return (
    <div
      data-testid="loading-overlay"
      className={cn(
        scope === "page" ? "fixed inset-0 z-[60]" : "absolute inset-0 z-10",
        "flex items-center justify-center bg-background/60 backdrop-blur-sm",
        className,
      )}
      aria-modal="true"
      role="dialog"
    >
      <div className="mx-4 w-full max-w-sm rounded-xl border bg-background p-4 shadow-sm">
        <div className="flex items-start gap-3">
          <Spinner size="lg" className="mt-0.5 shrink-0" />
          <div className="grid flex-1 gap-3">
            <div className="text-sm font-semibold">{title}</div>
            <div className="text-sm text-muted-foreground" data-testid="loading-message">
              {message ?? "Por favor espera..."}
            </div>
            {normalizedProgress != null ? (
              <div className="grid gap-1">
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
                    style={{ width: `${normalizedProgress}%` }}
                  />
                </div>
                <div className="text-xs text-muted-foreground">{normalizedProgress.toFixed(0)}%</div>
              </div>
            ) : null}
            {details?.length ? (
              <div className="grid gap-1 text-xs text-muted-foreground">
                {details.map((item) => (
                  <div key={item}>{item}</div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

export { LoadingOverlay }
