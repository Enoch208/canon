import { Icon } from "@/components/icon"
import { CTA, Section, StatBlock, TruthTransition } from "@/components/landing"
import { HeroBackground } from "@/components/hero-background"
import { MaskedHeading } from "@/components/masked-heading"
import { Reveal } from "@/components/reveal"
import { getConflict, getDashboard, getResults } from "@/lib/api"

export const dynamic = "force-dynamic"

const DEMO_ID = "qst_0428"

const PIPELINE = [
  {
    icon: "search-01",
    title: "Retrieve",
    body: "SQLite FTS5 BM25 over every indexed document. Identical for both arms — Canon does not change the retriever.",
  },
  {
    icon: "database-01",
    title: "Resolve in HydraDB",
    body: "Candidate documents are walked back to their claim keys. The graph returns the current proposition, the retired ones, and the supersession chain that connects them.",
  },
  {
    icon: "filter",
    title: "Rebuild the context",
    body: "Documents that assert a superseded value are replaced by the next candidate from the same ranking. History stays queryable; it just stops arriving as present tense.",
  },
  {
    icon: "quill-write-01",
    title: "Answer",
    body: "The same model and the same prompt as the baseline. Only the context topology changed.",
  },
]

export default async function LandingPage() {
  const [dashboard, results, demo] = await Promise.all([
    getDashboard(),
    getResults(),
    getConflict(DEMO_ID),
  ])

  const summary = results.summary
  const baselineLeak = summary.baseline_retired_gold_doc_in_context as number
  const canonLeak = summary.canon_retired_gold_doc_in_context as number
  const total = summary.conflict_questions as number
  const retired = demo.retired_evidence[0]
  const current = demo.current_evidence[0]

  return (
    <div className="pb-24">
      <section className="relative flex flex-col items-center overflow-hidden px-6 pb-10 md:pb-12">
        <HeroBackground />
        <div className="relative z-10 mx-auto w-full max-w-[1100px] pt-8 text-center md:pt-10">
          <Reveal delay={40}>
            <span className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3.5 py-1.5 text-xs font-light tracking-wide text-accent">
              <Icon name="time-quarter-pass" size={14} />
              Temporal truth integrity · HydraDB OSS · EnterpriseRAG-Bench
            </span>
          </Reveal>

          <MaskedHeading
            text="Old truth shouldn't become new context."
            delay={120}
            className="mt-10 text-4xl font-extralight tracking-[-0.04em] text-balance md:text-6xl lg:text-7xl"
          />

          <Reveal as="p" delay={220} className="mx-auto mt-8 max-w-2xl">
            <span className="text-base leading-relaxed font-extralight text-muted md:text-lg">
              Retrieval optimises for relevance. A superseded claim is still relevant — which is why
              it keeps arriving as if it were current. Canon resolves claim history in HydraDB
              before an answer is grounded.
            </span>
          </Reveal>

          <Reveal delay={300} className="mt-12">
            <div className="flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
              <CTA href="/truth" primary icon="dashboard-square-01">
                Open the dashboard
              </CTA>
              <CTA href={`/change/${DEMO_ID}`} icon="microscope">
                Inspect a truth change
              </CTA>
            </div>
          </Reveal>

          <Reveal delay={380} className="mt-16">
            <TruthTransition
              retiredValue={demo.retired_values[0]}
              retiredSpan={retired.evidence_span}
              retiredSource={retired.source_type}
              retiredDocId={retired.doc_id}
              currentValue={demo.current_value ?? ""}
              currentSpan={current.evidence_span}
              currentSource={current.source_type}
              currentDocId={current.doc_id}
              transition={demo.transition}
              temporalQuality={demo.temporal_quality}
            />
            <p className="mt-8 text-center text-xs font-light text-faint">
              Real spans from {demo.claim_key} — {dashboard.corpus_documents.toLocaleString()}{" "}
              EnterpriseRAG-Bench documents indexed.
            </p>
          </Reveal>
        </div>
      </section>

      <Section
        id="result"
        className="pt-16 pb-24 md:pt-20 md:pb-32"
        eyebrow="The result"
        title="Same corpus. Same retriever. Same prompt."
        lede="Only the context topology changes. Across all 20 official conflicting-information questions, this is how often a document that still asserts the retired value reached the model as present-tense context."
      >
        <div className="grid gap-8 md:grid-cols-3">
          <StatBlock
            value={`${baselineLeak}/${total}`}
            label="BM25 baseline"
            detail="The superseded document is retrieved and enters the context unmarked."
            tone="retired"
          />
          <StatBlock
            value={`${canonLeak}/${total}`}
            label="Canon grounding"
            detail="The one remaining case is contested — no supersession is established, so nothing is dropped."
            tone="accent"
          />
          <StatBlock
            value={`${summary.canon_current_gold_doc_in_context}/${total}`}
            label="Current evidence retrieved"
            detail={`Up from ${summary.baseline_current_gold_doc_in_context}/${total}: the graph pins current evidence the retriever ranked too low.`}
            tone="accent"
          />
        </div>
        <Reveal className="mt-12">
          <CTA href="/results" icon="chart-line-data-02">
            See the full benchmark
          </CTA>
        </Reveal>
      </Section>

      <Section
        id="how"
        eyebrow="How it works"
        title="A temporal claim graph between retrieval and generation."
        lede="Enterprise knowledge is time-bound assertions, not a bag of facts. Canon models the difference explicitly."
      >
        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-2">
          {PIPELINE.map((step, index) => (
            <Reveal key={step.title} delay={index * 60} className="bg-canvas p-8">
              <Icon name={step.icon} size={52} className="text-accent/70" />
              <p className="mt-6 font-mono text-[10px] tracking-[0.2em] text-faint uppercase">
                Step {index + 1}
              </p>
              <h3 className="mt-2 text-xl font-light tracking-tight">{step.title}</h3>
              <p className="mt-3 text-sm leading-relaxed font-light text-muted">{step.body}</p>
            </Reveal>
          ))}
        </div>
      </Section>

      <Section
        id="graph"
        eyebrow="Why HydraDB"
        title="The graph decides which evidence is current."
        lede="Not a visualisation layer. Remove HydraDB and the answers change — three graph operations run on every question."
      >
        <div className="grid gap-8 md:grid-cols-4">
          <StatBlock
            value={dashboard.claim_keys.toLocaleString()}
            label="Claim keys"
            detail="One mutable property of one entity."
          />
          <StatBlock
            value={(dashboard.graph_counts.Assertion ?? 0).toLocaleString()}
            label="Assertions"
            detail="Each with an exact evidence span and source document."
          />
          <StatBlock
            value={(dashboard.graph_counts.SUPERSEDES ?? 0).toLocaleString()}
            label="Supersession edges"
            detail="Canon events that replaced an earlier canon event."
          />
          <StatBlock
            value={dashboard.current_conflicts.toLocaleString()}
            label="Canon transitions"
            detail={`${dashboard.contested_claims} contested — order not established, no winner invented.`}
            tone="accent"
          />
        </div>
      </Section>

      <section className="border-t border-line px-6 py-24 md:py-32">
        <div className="mx-auto max-w-[1100px]">
          <Reveal className="rounded-lg border border-line bg-surface p-10 md:p-14">
            <h2 className="max-w-2xl text-2xl font-extralight tracking-[-0.03em] text-balance md:text-4xl">
              Ask it something, then ask what it used to be.
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-relaxed font-extralight text-muted">
              Every answer returns a state — CANON, CONTESTED or UNKNOWN — with the evidence behind
              it, the retired context that was filtered, and the HydraDB queries that produced it.
              Never prose alone.
            </p>
            <div className="mt-10 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
              <CTA href="/ask" primary icon="quill-write-01">
                Ask Canon
              </CTA>
              <CTA href="/entities" icon="user-multiple">
                Identity resolution
              </CTA>
            </div>
          </Reveal>
        </div>
      </section>
    </div>
  )
}
