"use client"

import { useState } from "react"

import { EvidenceCard, HydraQueryCard } from "@/components/evidence"
import { Icon } from "@/components/icon"
import { Field, Panel, StateBadge } from "@/components/primitives"
import type { AskResponse } from "@/lib/api"

const MODES = [
  { id: "current", label: "Current", hint: "What is X now?" },
  { id: "historical", label: "Historical", hint: "What was X before the update?" },
]

const DISPOSITION_LABEL: Record<string, string> = {
  current_evidence: "current evidence",
  superseded_for_current_grounding: "superseded",
  historical_evidence: "historical",
  contested_evidence: "contested",
  not_in_claim_graph: "unlinked",
}

export function AskClient({ samples }: { samples: string[] }) {
  const [question, setQuestion] = useState(samples[0] ?? "")
  const [mode, setMode] = useState("current")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<AskResponse | null>(null)

  async function submit(next: string, nextMode: string) {
    setPending(true)
    setError(null)
    try {
      const result = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: next, mode: nextMode }),
      })
      if (!result.ok) {
        throw new Error(`ask failed with ${result.status}`)
      }
      setResponse((await result.json()) as AskResponse)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "request failed")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault()
          void submit(question, mode)
        }}
      >
        <div className="flex items-center gap-3 rounded-lg border border-line bg-surface px-5 py-4">
          <Icon name="search-01" size={24} className="text-line-strong" />
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about a current or historical value"
            className="flex-1 bg-transparent text-sm font-light text-ink outline-none placeholder:text-faint"
          />
          <button
            type="submit"
            disabled={pending || question.trim().length === 0}
            className="rounded-md border border-line-strong px-4 py-2 text-xs font-light tracking-[0.14em] text-ink uppercase transition-colors hover:border-accent hover:text-accent disabled:opacity-40"
          >
            {pending ? "Resolving" : "Ask"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {MODES.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setMode(option.id)}
              className={`rounded-full border px-4 py-1.5 text-xs font-light transition-colors ${
                mode === option.id
                  ? "border-accent/50 text-accent"
                  : "border-line text-faint hover:text-ink"
              }`}
            >
              {option.label}
              <span className="pl-2 text-faint">{option.hint}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {samples.map((sample) => (
            <button
              key={sample}
              type="button"
              onClick={() => {
                setQuestion(sample)
                void submit(sample, mode)
              }}
              className="max-w-full truncate rounded-md border border-line px-3 py-1.5 text-left text-[11px] font-light text-faint transition-colors hover:border-line-strong hover:text-muted"
            >
              {sample}
            </button>
          ))}
        </div>
      </form>

      {error ? (
        <p className="rounded-md border border-retired/40 bg-surface px-4 py-3 text-sm font-light text-retired">
          {error}
        </p>
      ) : null}

      {response ? (
        <div className="flex flex-col gap-4">
          <section className="rounded-lg border border-line bg-surface p-8">
            <div className="flex flex-wrap items-center gap-4 pb-6">
              <StateBadge state={response.state} />
              <span className="font-mono text-[11px] text-faint">
                retrieval {response.retrieval_ms} ms · grounding {response.grounding_ms} ms
              </span>
            </div>
            <p className="text-4xl font-extralight tracking-[-0.04em] text-accent">
              {response.answer_value ?? "UNKNOWN"}
            </p>
            <div className="grid gap-6 pt-8 sm:grid-cols-3">
              <Field label="Why">{response.why}</Field>
              <Field label="Claim key">
                <span className="font-mono text-xs">{response.claim_key ?? "none matched"}</span>
              </Field>
              <Field label="Retired context filtered">
                {response.retired_evidence_filtered}{" "}
                {response.retired_evidence_filtered === 1 ? "document" : "documents"}
              </Field>
            </div>
          </section>

          {response.evidence.length > 0 ? (
            <Panel title="Grounding evidence">
              <div className="flex flex-col gap-3">
                {response.evidence.map((row) => (
                  <EvidenceCard
                    key={row.doc_id + row.evidence_span}
                    evidence={row}
                    tone={response.mode === "historical" ? "retired" : "current"}
                  />
                ))}
              </div>
            </Panel>
          ) : null}

          <Panel title="Candidate documents" subtitle="BM25 top-k, labelled by the claim graph">
            <ul className="flex flex-col divide-y divide-line">
              {response.documents.map((doc) => (
                <li key={doc.doc_id} className="flex items-center gap-4 py-3">
                  <span
                    className={`w-6 shrink-0 font-mono text-[11px] ${doc.kept ? "text-accent" : "text-retired"}`}
                  >
                    {doc.rank ?? "+"}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-light text-muted">
                    {doc.title || doc.doc_id}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-faint">
                    {DISPOSITION_LABEL[doc.disposition] ?? doc.disposition}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="HydraDB queries">
            <div className="flex flex-col gap-3">
              {response.query_cards.map((card) => (
                <HydraQueryCard key={card.query_id} card={card} />
              ))}
            </div>
          </Panel>
        </div>
      ) : null}
    </div>
  )
}
