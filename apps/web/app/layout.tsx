import type { Metadata } from "next"
import type { ReactNode } from "react"

import { Nav } from "@/components/nav"

import "./globals.css"

export const metadata: Metadata = {
  title: "Canon — temporal truth integrity",
  description:
    "Canon resolves claim history in HydraDB before an answer is grounded, so retired enterprise values stop entering present-tense context.",
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-canvas font-sans text-ink antialiased">
        <Nav />
        <main className="pt-24">{children}</main>
        <footer className="border-t border-line px-6 py-10">
          <div className="mx-auto flex max-w-[1100px] flex-col gap-3 text-xs font-light text-faint sm:flex-row sm:items-center sm:justify-between">
            <span>HydraDB OSS decides which evidence is current before it reaches the model.</span>
            <span className="font-mono">EnterpriseRAG-Bench · 511,958 documents indexed</span>
          </div>
        </footer>
      </body>
    </html>
  )
}
