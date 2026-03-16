"use client"

import * as React from "react"
import { Loader2Icon } from "lucide-react"

import { cn } from "@/lib/utils"

type SpinnerProps = React.ComponentProps<"div"> & {
  size?: "sm" | "md" | "lg"
}

function Spinner({ className, size = "md", ...props }: SpinnerProps) {
  const iconSize = size === "sm" ? "size-4" : size === "lg" ? "size-7" : "size-5"

  return (
    <div
      data-testid="spinner"
      role="status"
      aria-live="polite"
      aria-label="Cargando"
      className={cn("inline-flex items-center justify-center", className)}
      {...props}
    >
      <Loader2Icon className={cn(iconSize, "animate-spin")} />
    </div>
  )
}

export { Spinner }
