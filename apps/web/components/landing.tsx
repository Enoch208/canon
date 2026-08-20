import Link from "next/link"
import type { ReactNode } from "react"

import { Icon } from "@/components/icon"
import { Reveal } from "@/components/reveal"

export function Section({
  id,
  eyebrow,
  title,
  lede,
  children,
  className = "",
}: {
  id: string
  eyebrow: string
  title: string
  lede?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section
      id={id}
      className={`border-t border-line px-6 ${className || "py-24 md:py-32"}`}
    >
      <div className="mx-auto max-w-[1100px]">
        <Reveal>
          <p className="text-[10px] font-light tracking-[0.22em] text-accent uppercase">
            {eyebrow}
          </p>
          <h2 className="mt-5 max-w-3xl text-3xl font-extralight tracking-[-0.03em] text-balance md:text-5xl">
            {title}
          </h2>
          {lede ? (
            <p className="mt-6 max-w-2xl text-base leading-relaxed font-extralight text-muted md:text-lg">
              {lede}
            </p>
          ) : null}
        </Reveal>
        <div className="mt-14">{children}</div>
      </div>
    </section>
  )
}

export function TruthTransition({
  retiredValue,
  retiredSpan,
  retiredSource,
  retiredDocId,
  currentValue,
  currentSpan,
  currentSource,
  currentDocId,
  transition,
  temporalQuality,
}: {
  retiredValue: string
  retiredSpan: string
  retiredSource: string
  retiredDocId: string
  currentValue: string
  currentSpan: string
  currentSource: string
  currentDocId: string
  transition: string
  temporalQuality: string
}) {
  return (
    <div className="mx-auto max-w-[860px] overflow-hidden rounded-xl border border-line bg-surface/80 backdrop-blur-sm">
      <div className="grid md:grid-cols-2">
        <EvidenceSide
          kind="retired"
          value={retiredValue}
          span={retiredSpan}
          source={retiredSource}
          docId={retiredDocId}
        />
        <EvidenceSide
          kind="current"
          value={currentValue}
          span={currentSpan}
          source={currentSource}
          docId={currentDocId}
        />
      </div>
      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-t border-line bg-canvas/60 px-5 py-3">
        <Icon name="arrow-right-01" size={13} className="text-faint" />
        <span className="text-[10px] font-light tracking-[0.18em] text-muted uppercase">
          {transition.replace(/_/g, " ")}
        </span>
        <span className="text-faint">·</span>
        <span className="font-mono text-[10px] text-accent">{temporalQuality} verified</span>
      </div>
    </div>
  )
}

function EvidenceSide({
  kind,
  value,
  span,
  source,
  docId,
}: {
  kind: "retired" | "current"
  value: string
  span: string
  source: string
  docId: string
}) {
  const retired = kind === "retired"
  return (
    <div
      className={`p-6 md:p-7 ${retired ? "border-b border-line md:border-r md:border-b-0" : ""}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span
          className={`text-[10px] font-light tracking-[0.2em] uppercase ${
            retired ? "text-retired" : "text-accent"
          }`}
        >
          {retired ? "Retired" : "Current"}
        </span>
        <span className="font-mono text-[10px] text-faint">{source}</span>
      </div>
      <p
        className={`mt-3 font-mono text-lg font-light tracking-tight md:text-xl ${
          retired ? "text-retired/80 line-through decoration-retired/40" : "text-accent"
        }`}
      >
        {value}
      </p>
      <p className="mt-3 text-[13px] leading-relaxed font-light text-muted">
        &ldquo;{span}&rdquo;
      </p>
      <p className="mt-3 truncate font-mono text-[10px] text-faint">{docId}</p>
    </div>
  )
}

export function StatBlock({
  value,
  label,
  detail,
  tone = "ink",
}: {
  value: string
  label: string
  detail?: string
  tone?: "ink" | "accent" | "retired"
}) {
  const color =
    tone === "accent" ? "text-accent" : tone === "retired" ? "text-retired" : "text-ink"
  return (
    <div className="border-t border-line pt-5">
      <p className={`font-mono text-3xl font-light tabular-nums md:text-4xl ${color}`}>{value}</p>
      <p className="mt-3 text-sm font-light text-ink">{label}</p>
      {detail ? (
        <p className="mt-2 text-xs leading-relaxed font-light text-faint">{detail}</p>
      ) : null}
    </div>
  )
}

export function CTA({
  href,
  children,
  primary = false,
  icon,
}: {
  href: string
  children: ReactNode
  primary?: boolean
  icon: string
}) {
  const className = primary
    ? "bg-ink text-canvas hover:bg-white"
    : "border border-line bg-surface text-muted hover:border-line-strong hover:text-ink"
  return (
    <Link
      href={href}
      className={`flex w-full items-center justify-center gap-2 rounded-full px-7 py-3.5 text-sm font-medium transition-all active:scale-95 sm:w-auto ${className}`}
    >
      <Icon name={icon} size={17} />
      {children}
    </Link>
  )
}
