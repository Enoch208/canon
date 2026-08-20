import Link from "next/link"
import { notFound } from "next/navigation"

import { EvidenceCard, HydraQueryCard } from "@/components/evidence"
import { Icon } from "@/components/icon"
import { Field, Panel, StateBadge } from "@/components/primitives"
import { Page } from "@/components/shell"
import { getConflict } from "@/lib/api"

export const dynamic = "force-dynamic"

export default async function TruthChangePage({ params }: { params: Promise<{ questionId: string }> }) {
  const { questionId } = await params
  const change = await getConflict(questionId).catch(() => null)
  if (!change) {
    notFound()
  }

  return (
    <Page
      eyebrow={change.question_id}
      title={change.entity}
      lede={change.predicate.replace(/_/g, " ")}
      actions={<StateBadge state={change.state} />}
    >
      <Link
        href="/truth"
        className="mb-10 inline-flex items-center gap-2 text-xs font-light tracking-[0.14em] text-faint uppercase transition-colors hover:text-ink"
      >
        <Icon name="arrow-left-01" size={16} />
        All truth changes
      </Link>

      <section className="grid gap-4 pb-12 lg:grid-cols-[1fr_auto_1fr]">
        <div className="rounded-lg border border-retired/30 bg-surface p-8">
          <span className="text-[10px] font-light tracking-[0.18em] text-faint uppercase">
            Retired
          </span>
          <p className="pt-4 text-3xl font-extralight tracking-[-0.03em] text-retired">
            {change.retired_values.join(", ") || "—"}
          </p>
        </div>
        <div className="flex flex-col items-center justify-center gap-3 px-4">
          <Icon name="arrow-right-double" size={40} className="text-line-strong" />
          <span className="text-center text-[10px] font-light tracking-[0.16em] text-faint uppercase">
            {change.transition}
          </span>
        </div>
        <div className="rounded-lg border border-accent/30 bg-surface p-8">
          <span className="text-[10px] font-light tracking-[0.18em] text-faint uppercase">
            Current
          </span>
          <p className="pt-4 text-3xl font-extralight tracking-[-0.03em] text-accent">
            {change.current_value ?? (change.contested_values.join(" / ") || "—")}
          </p>
        </div>
      </section>

      <section className="grid gap-4 pb-12 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-line bg-surface p-6">
          <Field label="Temporal quality">{change.temporal_quality}</Field>
        </div>
        <div className="rounded-lg border border-line bg-surface p-6">
          <Field label="Canon events">{change.events.length}</Field>
        </div>
        <div className="rounded-lg border border-line bg-surface p-6">
          <Field label="Verified structured residue">
            {change.residue.filter((row) => row.residue_class === "VERIFIED_STRUCTURED").length}
          </Field>
        </div>
        <div className="rounded-lg border border-line bg-surface p-6">
          <Field label="Lexical restatements">
            {change.residue.filter((row) => row.residue_class === "LEXICAL_RESTATEMENT").length}
          </Field>
        </div>
      </section>

      <div className="flex flex-col gap-4 pb-12">
        <Panel title="Evidence" subtitle="Exact spans from the benchmark corpus">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="flex flex-col gap-3">
              <span className="text-[10px] font-light tracking-[0.18em] text-retired uppercase">
                Superseded for current grounding
              </span>
              {change.retired_evidence.map((row) => (
                <EvidenceCard key={row.doc_id + row.evidence_span} evidence={row} tone="retired" />
              ))}
            </div>
            <div className="flex flex-col gap-3">
              <span className="text-[10px] font-light tracking-[0.18em] text-accent uppercase">
                Current
              </span>
              {change.current_evidence.map((row) => (
                <EvidenceCard key={row.doc_id + row.evidence_span} evidence={row} tone="current" />
              ))}
            </div>
          </div>
        </Panel>

        <Panel
          title="Residue"
          subtitle="Every document that still carries the retired value, including the superseded source itself"
        >
          {change.residue.length === 0 ? (
            <p className="text-sm font-light text-faint">
              No residue recorded for this claim. Zero findings are shown as zero.
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {change.residue.map((row) => (
                <EvidenceCard key={row.doc_id + row.evidence_span} evidence={row} tone="retired" />
              ))}
            </div>
          )}
        </Panel>

        <Panel title="HydraDB queries" subtitle="Every query that produced this page">
          <div className="flex flex-col gap-3">
            {change.query_cards.map((card) => (
              <HydraQueryCard key={card.query_id} card={card} />
            ))}
          </div>
        </Panel>
      </div>
    </Page>
  )
}
