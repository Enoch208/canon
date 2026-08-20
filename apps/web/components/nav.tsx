"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"

import { Icon } from "@/components/icon"
import { Wordmark } from "@/components/wordmark"

const NAV = [
  { href: "/truth", label: "Truth" },
  { href: "/residue", label: "Residue" },
  { href: "/entities", label: "Identities" },
  { href: "/results", label: "Results" },
  { href: "/ask", label: "Ask" },
]

export function Nav() {
  const [scrolled, setScrolled] = useState(false)
  const pathname = usePathname()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <header className="fixed top-0 right-0 left-0 z-50 flex w-full justify-center px-4 pt-4 md:pt-6">
      <nav
        className={`relative flex w-full items-center justify-between rounded-full border backdrop-blur-xl transition-all duration-500 ease-out ${
          scrolled
            ? "max-w-3xl border-white/12 bg-canvas/85 py-2 pr-2 pl-5 shadow-[0_8px_30px_rgba(0,0,0,0.5),inset_0_1px_0_0_rgba(255,255,255,0.06)]"
            : "max-w-4xl border-white/10 bg-raised/60 py-2.5 pr-2.5 pl-6 shadow-[0_4px_24px_rgba(0,0,0,0.35),inset_0_1px_0_0_rgba(255,255,255,0.05)]"
        }`}
      >
        <Link href="/" aria-label="Canon home" className="transition-transform active:scale-95">
          <Wordmark size={scrolled ? 19 : 21} />
        </Link>

        <div className="hidden flex-1 md:block" />

        <div className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-full px-3.5 py-1.5 text-sm font-light transition-colors duration-200 ${
                  active ? "bg-white/8 text-ink" : "text-muted hover:bg-white/5 hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            )
          })}
        </div>

        <div className="hidden flex-1 md:block" />

        <Link
          href="/truth"
          className="flex items-center justify-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-medium text-canvas transition-all duration-200 hover:bg-white active:scale-95"
        >
          <Icon name="dashboard-square-01" className="text-[15px]" />
          <span className="hidden sm:inline">Dashboard</span>
        </Link>
      </nav>
    </header>
  )
}
