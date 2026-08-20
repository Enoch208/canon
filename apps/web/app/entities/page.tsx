import { Panel } from "@/components/primitives"
import { Page } from "@/components/shell"
import { getEntities } from "@/lib/api"

export const dynamic = "force-dynamic"

const ORDER = ["RESOLVED", "PROBABLE", "AMBIGUOUS"]

export default async function IdentitiesPage() {
  const report = await getEntities()

  return (
    <Page
      eyebrow={"Identity"}
      title={"Aliases resolved to people, with the binding that proves it."}
      lede={"Every edge comes from a line that appears verbatim in the corpus. Ambiguity stays visible."}
    >
      <section className="flex flex-col gap-4 pb-10">
        <p className="max-w-2xl text-sm leading-relaxed font-light text-muted">
          Every alias comes from a real <span className="font-mono text-xs">Name &lt;email&gt;</span>{" "}
          binding in a source document. An alias that maps to more than one person stays ambiguous —
          Canon never silently merges two people who share a name.
        </p>
        <div className="flex flex-wrap gap-x-8 gap-y-1 font-mono text-[11px] text-faint">
          <span>{report.corpus.documents_scanned.toLocaleString()} documents scanned</span>
          <span>{report.corpus.bindings_found.toLocaleString()} bindings</span>
          <span>{report.corpus.people.toLocaleString()} people</span>
          <span>{report.corpus.aliases.toLocaleString()} aliases</span>
        </div>
      </section>

      <section className="grid gap-4 pb-10 sm:grid-cols-3">
        {ORDER.map((state) => (
          <div key={state} className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-6">
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-[10px] font-light tracking-[0.14em] text-faint uppercase">
                {state}
              </span>
              <span className="text-3xl font-extralight tabular-nums">
                {(report.materialised[state] ?? 0).toLocaleString()}
              </span>
            </div>
            <p className="text-xs leading-relaxed font-light text-muted">
              {report.definition[state]}
            </p>
          </div>
        ))}
      </section>

      <p className="pb-6 text-xs leading-relaxed font-light text-faint">{report.note}</p>

      <Panel title="Aliases in the graph" subtitle="Alias -RESOLVES_TO-> Person, with source evidence">
        <ul className="flex flex-col divide-y divide-line">
          {report.aliases.map((alias) => (
            <li key={`${alias.resolution}-${alias.alias_type}-${alias.value}`} className="flex flex-col gap-2 py-5">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] font-light tracking-[0.14em] text-faint uppercase">
                <span className={alias.resolution === "AMBIGUOUS" ? "text-retired" : "text-accent"}>
                  {alias.resolution}
                </span>
                <span>{alias.alias_type.replace(/_/g, " ")}</span>
                <span>{alias.support.toLocaleString()} bindings</span>
                <span>
                  {alias.candidate_count} candidate{alias.candidate_count === 1 ? "" : "s"}
                </span>
              </div>
              <p className="font-mono text-sm text-ink">{alias.value}</p>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-light text-muted">
                {alias.candidates.map((person) => (
                  <span key={`${person.name}-${person.organization}`}>
                    {person.name} · <span className="text-faint">{person.organization}</span>
                  </span>
                ))}
              </div>
              <p className="truncate text-xs leading-relaxed font-light text-muted">
                {alias.evidence_span}
              </p>
              <p className="font-mono text-[10px] text-faint">{alias.evidence_doc_id}</p>
            </li>
          ))}
        </ul>
      </Panel>
    </Page>
  )
}
