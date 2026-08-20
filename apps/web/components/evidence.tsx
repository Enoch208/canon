import { Icon } from "@/components/icon"

import type { Evidence, QueryCard } from "@/lib/api"

const SOURCE_ICONS: Record<string, string> = {
  jira: "ticket-01",
  linear: "task-01",
  confluence: "book-open-01",
  google_drive: "folder-01",
  gmail: "mail-01",
  slack: "message-multiple-01",
  github: "github",
  hubspot: "user-group",
  fireflies: "mic-01",
}

export function EvidenceCard({ evidence, tone }: { evidence: Evidence; tone: "current" | "retired" }) {
  const border = tone === "current" ? "border-accent/30" : "border-retired/30"
  return (
    <article className={`flex gap-4 rounded-md border ${border} bg-raised p-4`}>
      <Icon
        name={SOURCE_ICONS[evidence.source_type] ?? "file-01"}
        size={32}
        className="shrink-0 text-line-strong"
      />
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-light tracking-[0.14em] text-faint uppercase">
          <span>{evidence.source_type}</span>
          <span>{evidence.stance}</span>
          {evidence.asserted_at ? <span>{evidence.asserted_at}</span> : null}
          {evidence.residue_class ? (
            <span className="text-retired">{evidence.residue_class.replace(/_/g, " ")}</span>
          ) : null}
          <span>{evidence.discovery.replace(/_/g, " ")}</span>
        </div>
        <p className="truncate text-sm font-light text-ink">{evidence.title || evidence.doc_id}</p>
        <p className="text-sm leading-relaxed font-light text-muted">{evidence.evidence_span}</p>
        <p className="font-mono text-[10px] text-faint">{evidence.doc_id}</p>
      </div>
    </article>
  )
}

export function HydraQueryCard({ card }: { card: QueryCard }) {
  return (
    <details className="group rounded-md border border-line bg-raised">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3">
        <span className="flex items-center gap-3 text-sm font-light text-ink">
          <Icon name="database-02" size={24} className="text-accent" />
          {card.operation}
        </span>
        <span className="font-mono text-[10px] text-faint">
          {card.result_count} rows · {card.client_round_trip_ms.toFixed(1)} ms round trip
        </span>
      </summary>
      <div className="flex flex-col gap-3 border-t border-line px-4 py-4">
        <pre className="overflow-x-auto rounded bg-canvas p-3 font-mono text-[11px] leading-relaxed text-muted">
          {card.cypher}
        </pre>
        <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-[10px] text-faint">
          <span>engine: {card.engine}</span>
          <span>query_id: {card.query_id}</span>
          <span>parameters: {JSON.stringify(card.parameters)}</span>
        </div>
      </div>
    </details>
  )
}
