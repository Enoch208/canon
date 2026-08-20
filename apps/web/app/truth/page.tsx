import { Icon } from "@/components/icon"
import Link from "next/link"

import { EvidenceCard } from "@/components/evidence"
import { Panel, StatTile, StateBadge } from "@/components/primitives"
import { Page } from "@/components/shell"
import { getConflicts, getDashboard, getResults } from "@/lib/api"

export const dynamic = "force-dynamic"

export default async function TruthDashboardPage() {
  const [dashboard, conflicts, results] = await Promise.all([
    getDashboard(),
    getConflicts(),
    getResults(),
  ])
  const summary = results.summary

  return (
    <Page
      eyebrow={"Truth dashboard"}
      title={"What is current, what was retired, and why."}
      lede={"Every number resolves from the HydraDB claim graph. Zeros are shown as zeros."}
    >
      <section className="flex flex-col gap-6 pb-14">
        <div className="flex flex-wrap gap-x-8 gap-y-2 font-mono text-xs text-faint">
          <span>{dashboard.corpus_documents.toLocaleString()} documents indexed</span>
          <span>{dashboard.claim_keys} claim keys extracted</span>
          <span>
            {dashboard.graph_counts.Assertion} assertions ·{" "}
            {dashboard.graph_counts.SUPERSEDES} supersession edges
          </span>
        </div>
      </section>

      <section className="grid gap-4 pb-14 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon="time-quarter-pass"
          label="Canon transitions"
          value={dashboard.current_conflicts}
          note="Claim keys where supersession is established"
          accent
        />
        <StatTile
          icon="help-square"
          label="Contested claims"
          value={dashboard.contested_claims}
          note="Order not established — no winner invented"
        />
        <StatTile
          icon="filter"
          label="Superseded docs filtered"
          value={`${summary.baseline_retired_gold_doc_in_context - summary.canon_retired_gold_doc_in_context}/${summary.baseline_retired_gold_doc_in_context}`}
          note="Retired evidence kept out of present-tense context"
          accent
        />
        <StatTile
          icon="search-visual"
          label="Retired values still in the corpus"
          value={dashboard.lexical_restatement_residue}
          note="Documents restating a retired value, every one inspectable"
        />
      </section>

      <section className="grid gap-4 pb-14 lg:grid-cols-3">
        <div className="rounded-lg border border-line bg-surface p-6 lg:col-span-2">
          <h2 className="text-sm font-light tracking-[0.12em] text-ink uppercase">
            Residue-aware retrieval
          </h2>
          <p className="pt-2 text-xs font-light text-faint">
            Canon reverse-traverses each retired value to find every document still carrying it,
            then keeps those documents out of present-tense context. Across all{" "}
            {summary.conflict_questions} official conflict questions:
          </p>
          <div className="grid gap-6 pt-8 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <span className="text-6xl font-extralight tracking-[-0.05em] text-retired tabular-nums">
                {summary.baseline_retired_gold_doc_in_context}
                <span className="text-2xl text-faint">/{summary.conflict_questions}</span>
              </span>
              <span className="text-xs font-light tracking-[0.14em] text-faint uppercase">
                BM25 baseline
              </span>
            </div>
            <div className="flex flex-col gap-2">
              <span className="text-6xl font-extralight tracking-[-0.05em] text-accent tabular-nums">
                {summary.canon_retired_gold_doc_in_context}
                <span className="text-2xl text-faint">/{summary.conflict_questions}</span>
              </span>
              <span className="text-xs font-light tracking-[0.14em] text-faint uppercase">
                Canon grounding
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-6">
          <Icon name="chart-histogram" size={48} className="text-line-strong" />
          <dl className="flex flex-col gap-3 text-sm font-light">
            <Row label="Current evidence retrieved" value={`${summary.canon_current_gold_doc_in_context}/${summary.conflict_questions}`} />
            <Row label="Baseline" value={`${summary.baseline_current_gold_doc_in_context}/${summary.conflict_questions}`} />
            <Row label="Historical query recovers retired" value={`${summary.historical_keeps_retired_gold}/${summary.conflict_questions}`} />
            <Row label="Grounding p95" value={`${summary.grounding_ms_p95} ms`} />
          </dl>
        </div>
      </section>

      <Panel title="Truth changes" subtitle="Every row resolved from the HydraDB claim graph">
        <ul className="flex flex-col divide-y divide-line">
          {conflicts.map((conflict) => (
            <li key={conflict.question_id}>
              <Link
                href={`/change/${conflict.question_id}`} className="flex flex-col gap-3 py-5 transition-opacity hover:opacity-80"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <StateBadge state={conflict.state} />
                  <span className="text-sm font-light text-ink">{conflict.entity}</span>
                  <span className="font-mono text-[11px] text-faint">{conflict.predicate}</span>
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm font-light">
                  {conflict.retired_values.map((value) => (
                    <span key={value} className="text-retired line-through decoration-retired/40">
                      {value}
                    </span>
                  ))}
                  {conflict.current_value ? (
                    <>
                      <Icon name="arrow-right-01" size={18} className="text-faint" />
                      <span className="text-accent">{conflict.current_value}</span>
                    </>
                  ) : (
                    <span className="text-faint">no value established</span>
                  )}
                  <span className="ml-auto font-mono text-[10px] text-faint">
                    {conflict.transition} · {conflict.temporal_quality}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </Page>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className="font-mono text-sm text-ink tabular-nums">{value}</dd>
    </div>
  )
}
