import { Icon } from "@/components/icon"
import { Panel } from "@/components/primitives"
import { Page } from "@/components/shell"
import { getResidue } from "@/lib/api"

export const dynamic = "force-dynamic"

const ORDER = [
  "VERIFIED_STRUCTURED",
  "LEXICAL_RESTATEMENT",
  "DERIVED_FREE_TEXT",
  "HISTORICAL_REFERENCE",
  "REJECTED_REFERENCE",
  "NOT_AN_ASSERTION",
]

export default async function ResiduePage() {
  const report = await getResidue()

  return (
    <Page
      eyebrow={"Residue"}
      title={"Where retired values still survive in the corpus."}
      lede={"Residue-aware retrieval is the mechanism; the classes below are what the sweep actually found."}
    >
      <section className="flex flex-col gap-4 pb-10">
        <p className="max-w-2xl text-sm leading-relaxed font-light text-muted">
          Where a retired value still survives in the corpus. Every row below is a real document and
          a real line — clicking a count reveals exactly that many records, and zero is shown as
          zero.
        </p>
      </section>

      <section className="grid gap-4 pb-10 sm:grid-cols-2 lg:grid-cols-3">
        {ORDER.map((name) => (
          <div key={name} className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-6">
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-[10px] font-light tracking-[0.14em] text-faint uppercase">
                {name.replace(/_/g, " ")}
              </span>
              <span className="text-3xl font-extralight tabular-nums">{report.counts[name] ?? 0}</span>
            </div>
            <p className="text-xs leading-relaxed font-light text-muted">{report.definition[name]}</p>
          </div>
        ))}
      </section>

      <Panel title="Records" subtitle={`${report.rows.length} inspectable rows`}>
        {report.rows.length === 0 ? (
          <p className="text-sm font-light text-faint">No residue recorded.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {report.rows.map((row) => (
              <li key={row.question_id + row.doc_id} className="flex flex-col gap-2 py-5">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] font-light tracking-[0.14em] text-faint uppercase">
                  <span className="text-retired">{row.residue_class.replace(/_/g, " ")}</span>
                  <span>{row.source_type}</span>
                  <span>{row.discovery.replace(/_/g, " ")}</span>
                  {row.source_field ? <span>field: {row.source_field}</span> : null}
                </div>
                <div className="flex flex-wrap items-center gap-3 text-sm font-light">
                  <span className="text-retired">{row.retired_value}</span>
                  <Icon name="arrow-right-01" size={16} className="text-faint" />
                  <span className="text-accent">{row.current_value ?? "—"}</span>
                  <span className="text-muted">· {row.entity}</span>
                </div>
                <p className="text-sm leading-relaxed font-light text-muted">{row.evidence_span}</p>
                <p className="font-mono text-[10px] text-faint">
                  {row.doc_id} · {row.question_id}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </Page>
  )
}
