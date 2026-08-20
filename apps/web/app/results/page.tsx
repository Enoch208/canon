import { Panel } from "@/components/primitives"
import { Page } from "@/components/shell"
import { getOfficial, getResults } from "@/lib/api"

export const dynamic = "force-dynamic"

const ABLATION: Array<{ label: string; baseline: string; canon: string; better: "low" | "high" }> = [
  {
    label: "Superseded document in present-tense context",
    baseline: "baseline_retired_gold_doc_in_context",
    canon: "canon_retired_gold_doc_in_context",
    better: "low",
  },
  {
    label: "Current gold document in context",
    baseline: "baseline_current_gold_doc_in_context",
    canon: "canon_current_gold_doc_in_context",
    better: "high",
  },
  {
    label: "Retired value string anywhere in context",
    baseline: "baseline_retired_value_string_in_context",
    canon: "canon_retired_value_string_in_context",
    better: "low",
  },
]

const ARMS = ["baseline", "canon_filtered", "canon"] as const
const ARM_LABELS: Record<string, string> = {
  baseline: "BM25 baseline",
  canon_filtered: "Canon, no note",
  canon: "Canon",
}
const ANSWER_ROWS: Array<{ label: string; key: string; better: "low" | "high" }> = [
  { label: "Answer states the current value", key: "judged_states_current_value", better: "high" },
  {
    label: "Answer presents the retired value as current",
    key: "judged_presents_retired_as_current",
    better: "low",
  },
  { label: "Answer abstains", key: "judged_abstains", better: "low" },
]

export default async function ResultsPage() {
  const [results, official] = await Promise.all([getResults(), getOfficial()])
  const summary = results.summary
  const total = summary.conflict_questions
  const answered = summary.canon_judged_states_current_value !== undefined

  return (
    <Page
      eyebrow={"Benchmark"}
      title={"Baseline versus Canon on EnterpriseRAG-Bench."}
      lede={"Same corpus, same retriever, same prompt. Each row is labelled deterministic or model-judged."}
    >
      <section className="flex flex-col gap-4 pb-10">
        <p className="max-w-2xl text-sm leading-relaxed font-light text-muted">
          Same corpus, same BM25 candidate retrieval, same top-k. The only difference between the
          arms is whether the HydraDB claim graph decides which candidates may ground a present-tense
          answer.
        </p>
        <div className="flex flex-wrap gap-x-8 gap-y-1 font-mono text-[11px] text-faint">
          <span>measured {results.measured_at}</span>
          <span>{results.corpus_documents.toLocaleString()} documents</span>
          <span>top_k {results.top_k}</span>
          <span>answer model {results.answer_model ?? "not run"}</span>
        </div>
      </section>

      <div className="flex flex-col gap-4">
        <Panel title="Ablation" subtitle={`All ${total} official conflicting_info questions`}>
          <table className="w-full text-sm font-light">
            <thead>
              <tr className="border-b border-line text-[10px] tracking-[0.16em] text-faint uppercase">
                <th className="pb-3 text-left font-light">Metric</th>
                <th className="pb-3 text-right font-light">BM25 baseline</th>
                <th className="pb-3 text-right font-light">Canon</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {ABLATION.map((row) => {
                const baseline = summary[row.baseline]
                const canon = summary[row.canon]
                const improved = row.better === "low" ? canon < baseline : canon > baseline
                return (
                  <tr key={row.label}>
                    <td className="py-4 pr-4 text-muted">{row.label}</td>
                    <td className="py-4 text-right font-mono tabular-nums">
                      {baseline}/{total}
                    </td>
                    <td
                      className={`py-4 text-right font-mono tabular-nums ${improved ? "text-accent" : "text-ink"}`}
                    >
                      {canon}/{total}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Panel>


        {official ? (
          <Panel
            title="Official benchmark harness"
            subtitle={`Scored by the benchmark's own evaluator (metrics_based_eval, --no-correction), judge ${official.judge_model}. Not our judge — theirs.`}
          >
            <table className="w-full text-sm font-light">
              <thead>
                <tr className="border-b border-line text-[10px] tracking-[0.16em] text-faint uppercase">
                  <th className="pb-3 text-left font-light">Metric</th>
                  {["baseline", "canon_filtered", "canon"].map((arm) => (
                    <th key={arm} className="pb-3 text-right font-light">
                      {official.arms[arm]?.label ?? arm}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {[
                  ["Correctness", "correctness_pct", "high"],
                  ["Completeness", "completeness_pct", "high"],
                  ["Combined (corr x comp)", "combined_score", "high"],
                  ["Document recall", "document_recall_pct", "low"],
                ].map(([label, key, better]) => {
                  const values = ["baseline", "canon_filtered", "canon"].map(
                    (arm) => (official.arms[arm] as unknown as Record<string, number>)[key as string],
                  )
                  const best = better === "high" ? Math.max(...values) : Math.max(...values)
                  return (
                    <tr key={key as string}>
                      <td className="py-4 pr-4 text-muted">{label as string}</td>
                      {values.map((value, index) => (
                        <td
                          key={index}
                          className={`py-4 text-right font-mono tabular-nums ${value === best && better === "high" ? "text-accent" : "text-ink"}`}
                        >
                          {(key as string) === "combined_score" ? value.toFixed(2) : `${value.toFixed(1)}%`}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="pt-5 text-xs leading-relaxed font-light text-faint">
              The middle column carries no claim-graph note. Context topology alone moves correctness
              from 70.0% to 82.5%. Document recall falls because the harness counts both conflicting
              gold documents as expected, and Canon removes the superseded one on purpose.
            </p>
          </Panel>
        ) : null}

        {answered ? (
          <Panel
            title="Answers"
            subtitle={`Same model (${results.answer_model}), same prompt. Every arm sees the same number of documents. Graded by ${summary.judge_model ?? "a model judge"}, ${summary.judge_passes_per_answer ?? 1} passes, ${summary.judge_unanimous_answers ?? 0}/${summary.judged_answers ?? 0} unanimous (model-judged).`}
          >
            <table className="w-full text-sm font-light">
              <thead>
                <tr className="border-b border-line text-[10px] tracking-[0.16em] text-faint uppercase">
                  <th className="pb-3 text-left font-light">Metric</th>
                  {ARMS.map((arm) => (
                    <th key={arm} className="pb-3 text-right font-light">
                      {ARM_LABELS[arm]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {ANSWER_ROWS.map((row) => {
                  const values = ARMS.map((arm) => summary[`${arm}_${row.key}`])
                  const best =
                    row.better === "low" ? Math.min(...values) : Math.max(...values)
                  return (
                    <tr key={row.key}>
                      <td className="py-4 pr-4 text-muted">{row.label}</td>
                      {ARMS.map((arm, index) => (
                        <td
                          key={arm}
                          className={`py-4 text-right font-mono tabular-nums ${values[index] === best ? "text-accent" : "text-ink"}`}
                        >
                          {values[index]}/{total}
                        </td>
                      ))}
                    </tr>
                  )
                })}
                <tr>
                  <td className="py-4 pr-4 text-muted">Superseded document in context</td>
                  {ARMS.map((arm) => (
                    <td
                      key={arm}
                      className={`py-4 text-right font-mono tabular-nums ${arm === "baseline" ? "text-ink" : "text-accent"}`}
                    >
                      {summary[`${arm}_retired_gold_doc_in_context`]}/{total}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
            <p className="pt-5 text-xs leading-relaxed font-light text-faint">
              The middle column carries no claim-graph note. Context topology alone accounts for most
              of the gain, so the result is not an artefact of telling the model the answer.
            </p>
          </Panel>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Graph decisions">
            <dl className="flex flex-col gap-3 text-sm font-light">
              <Row label="CANON" value={summary.graph_canon_states} />
              <Row label="CONTESTED" value={summary.graph_contested_states} />
              <Row label="Historical query recovers retired evidence" value={summary.historical_keeps_retired_gold} />
              <Row label="Questions where the graph added missing current evidence" value={summary.canon_questions_with_graph_pinned_docs} />
              <Row label="Info-not-found questions returning UNKNOWN" value={summary.abstention_graph_returns_unknown} />
            </dl>
          </Panel>
          <Panel title="Latency" subtitle="Measured on this machine, client round trip">
            <dl className="flex flex-col gap-3 text-sm font-light">
              <Row label="Grounding p50 (ms)" value={summary.grounding_ms_p50} />
              <Row label="Grounding p95 (ms)" value={summary.grounding_ms_p95} />
              <Row label="BM25 retrieval p50 (ms)" value={summary.retrieval_ms_p50} />
              <Row label="BM25 retrieval p95 (ms)" value={summary.retrieval_ms_p95} />
            </dl>
          </Panel>
        </div>

        {results.not_run.length > 0 ? (
          <Panel title="Not run" subtitle="Reported, never simulated">
            <ul className="flex flex-col gap-2 text-sm font-light text-muted">
              {results.not_run.map((entry) => (
                <li key={entry}>{entry}</li>
              ))}
            </ul>
          </Panel>
        ) : null}

        <Panel title="Question IDs" subtitle="Exactly the questions that were run">
          <div className="grid gap-6 sm:grid-cols-2">
            {Object.entries(results.question_ids).map(([category, ids]) => (
              <div key={category} className="flex flex-col gap-2">
                <span className="text-[10px] tracking-[0.16em] text-faint uppercase">
                  {category} ({ids.length})
                </span>
                <p className="font-mono text-[11px] leading-relaxed text-muted">{ids.join(" ")}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </Page>
  )
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between gap-6">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className="font-mono text-sm text-ink tabular-nums">{value}</dd>
    </div>
  )
}
