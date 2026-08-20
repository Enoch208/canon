import { Icon } from "@/components/icon"
import type { ReactNode } from "react"

export function StatTile({
  icon,
  label,
  value,
  note,
  accent,
}: {
  icon: string
  label: string
  value: number | string
  note?: string
  accent?: boolean
}) {
  return (
    <div className="flex flex-col gap-6 rounded-lg border border-line bg-surface p-6">
      <Icon name={icon} size={56} className={accent ? "text-accent" : "text-line-strong"} />
      <div className="flex flex-col gap-1">
        <span className="text-4xl font-extralight tracking-[-0.04em] tabular-nums">{value}</span>
        <span className="text-xs font-light tracking-[0.14em] text-faint uppercase">{label}</span>
        {note ? <span className="pt-2 text-xs font-light text-muted">{note}</span> : null}
      </div>
    </div>
  )
}

export function StateBadge({ state }: { state: string }) {
  const tone =
    state === "CANON"
      ? "border-accent/40 text-accent"
      : state === "CONTESTED"
        ? "border-retired/40 text-retired"
        : "border-line-strong text-faint"
  return (
    <span className={`inline-flex items-center rounded-full border px-3 py-1 text-[10px] font-light tracking-[0.16em] uppercase ${tone}`}
    >
      {state}
    </span>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[10px] font-light tracking-[0.18em] text-faint uppercase">{label}</span>
      <div className="text-sm font-light text-ink">{children}</div>
    </div>
  )
}

export function Panel({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-line bg-surface">
      <header className="border-b border-line px-6 py-4">
        <h2 className="text-sm font-light tracking-[0.12em] text-ink uppercase">{title}</h2>
        {subtitle ? <p className="pt-1 text-xs font-light text-faint">{subtitle}</p> : null}
      </header>
      <div className="px-6 py-5">{children}</div>
    </section>
  )
}
