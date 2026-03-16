"use client"

import * as React from "react"

import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

type Props = {
  open: boolean
  title?: string
  message?: string
  scope?: "page" | "section"
  className?: string
}

function LoadingOverlay({ open, title = "Cargando", message, scope = "section", className }: Props) {
  if (!open) return null

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
          <div className="grid gap-1">
            <div className="text-sm font-semibold">{title}</div>
            <div className="text-sm text-muted-foreground" data-testid="loading-message">
              {message ?? "Por favor espera..."}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export { LoadingOverlay }
