import type { ReactNode } from "react"

export function Page({
  eyebrow,
  title,
  lede,
  actions,
  children,
}: {
  eyebrow: string
  title: string
  lede?: string
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="mx-auto max-w-[1180px] px-6 pb-24">
      <header className="border-b border-line py-12">
        <p className="text-[10px] font-light tracking-[0.22em] text-accent uppercase">{eyebrow}</p>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-6">
          <h1 className="max-w-3xl text-3xl font-extralight tracking-[-0.03em] text-balance md:text-5xl">
            {title}
          </h1>
          {actions}
        </div>
        {lede ? (
          <p className="mt-6 max-w-2xl text-base leading-relaxed font-extralight text-muted">
            {lede}
          </p>
        ) : null}
      </header>
      <div className="py-12">{children}</div>
    </div>
  )
}
