"use client"

import { useEffect, useState } from "react"

import { Icon } from "@/components/icon"
import { StateBadge } from "@/components/primitives"
import type { AskResponse } from "@/lib/api"

const DISPOSITION_STYLE: Record<string, string> = {
  current_evidence: "border-accent/40 text-accent",
  superseded_for_current_grounding: "border-retired/50 text-retired",
  historical_evidence: "border-line-strong text-muted",
  contested_evidence: "border-line-strong text-muted",
  not_in_claim_graph: "border-line text-faint",
}

const DISPOSITION_LABEL: Record<string, string> = {
  current_evidence: "current",
  superseded_for_current_grounding: "superseded",
  historical_evidence: "historical",
  contested_evidence: "contested",
  not_in_claim_graph: "unlinked",
}

export function CutClient({
  question,
  questionId,
  oldValue,
  newValue,
  baselineAnswer,
  canonAnswer,
  baselineCorrect,
  canonCorrect,
  judgeModel,
}: {
  question: string
  questionId: string
  oldValue: string
  newValue: string
  baselineAnswer: string | null
  canonAnswer: string | null
  baselineCorrect: boolean | null
  canonCorrect: boolean | null
  judgeModel: string | null
}) {
  const [mode, setMode] = useState<"current" | "historical">("current")
  const [byMode, setByMode] = useState<Record<string, AskResponse | null>>({})
  const response = byMode[mode] ?? null

  useEffect(() => {
    let alive = true
    for (const m of ["current", "historical"] as const) {
      fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, mode: m }),
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (alive) setByMode((prev) => ({ ...prev, [m]: data as AskResponse }))
        })
        .catch(() => undefined)
    }
    return () => {
      alive = false
    }
  }, [question])

  const kept = response?.documents.filter((d) => d.kept) ?? []
  const backfill = response?.backfill_doc_ids ?? []

  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-wrap items-center gap-4">
        <span className="font-mono text-xs text-faint">{questionId}</span>
        <p className="max-w-3xl text-sm font-light text-muted">{question}</p>
        <div className="flex gap-2">
          {(["current", "historical"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`rounded-full border px-4 py-1.5 text-xs font-light tracking-[0.1em] uppercase transition-colors ${
                mode === m ? "border-accent/50 text-accent" : "border-line text-faint hover:text-ink"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-[1fr_auto_1fr]">
        <div className="min-w-0 rounded-lg border border-line bg-surface p-6">
          <p className="text-[10px] font-light tracking-[0.2em] text-faint uppercase">
            BM25 · relevant
          </p>
          <ul className="flex flex-col gap-2 pt-4">
            {(response?.documents ?? []).map((doc) => {
              const dropped = doc.disposition === "superseded_for_current_grounding" && mode === "current"
              const staleSpan = dropped
                ? (doc.evidence_span ??
                  response?.evidence.find((row) => row.doc_id === doc.doc_id)?.evidence_span)
                : null
              return (
                <li
                  key={doc.doc_id}
                  className={`flex flex-col gap-1.5 rounded-md border px-4 py-2.5 text-xs font-light ${
                    dropped ? "border-retired/50 bg-retired/[0.05]" : "border-line"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="w-5 font-mono text-faint">{doc.rank}</span>
                    <span className={`min-w-0 flex-1 truncate ${dropped ? "text-retired line-through decoration-retired/50" : "text-muted"}`}>
                      {doc.title || doc.doc_id}
                    </span>
                    <span className={`rounded border px-2 py-0.5 font-mono text-[10px] ${DISPOSITION_STYLE[doc.disposition] ?? "border-line text-faint"}`}>
                      {DISPOSITION_LABEL[doc.disposition] ?? doc.disposition}
                    </span>
                  </div>
                  {staleSpan ? (
                    <p className="pl-8 font-mono text-[11px] leading-relaxed text-retired/80">
                      &ldquo;{staleSpan}&rdquo;
                    </p>
                  ) : null}
                </li>
              )
            })}
          </ul>
        </div>

        <div className="flex flex-col items-center justify-center gap-2 px-2">
          <Icon name="arrow-right-01" size={26} className="rotate-90 text-line-strong lg:rotate-0" />
          <span className="text-center font-mono text-[10px] tracking-[0.18em] text-accent uppercase">
            Temporal
            <br />
            Cut
          </span>
        </div>

        <div className="min-w-0 rounded-lg border border-line bg-surface p-6">
          <p className="text-[10px] font-light tracking-[0.2em] text-faint uppercase">
            HydraDB · {mode === "current" ? "currently valid" : "historically valid"}
          </p>
          <ul className="flex flex-col gap-2 pt-4">
            {kept.map((doc) => (
              <li
                key={doc.doc_id}
                className="flex items-center gap-3 rounded-md border border-line px-4 py-2.5 text-xs font-light"
              >
                <span className="w-5 font-mono text-faint">{doc.rank}</span>
                <span className="min-w-0 flex-1 truncate text-muted">{doc.title || doc.doc_id}</span>
                <span className={`rounded border px-2 py-0.5 font-mono text-[10px] ${DISPOSITION_STYLE[doc.disposition] ?? "border-line text-faint"}`}>
                  {DISPOSITION_LABEL[doc.disposition] ?? doc.disposition}
                </span>
              </li>
            ))}
            {mode === "current"
              ? backfill.map((docId) => (
                  <li
                    key={docId}
                    className="flex items-center gap-3 rounded-md border border-accent/40 bg-accent/[0.05] px-4 py-2.5 text-xs font-light"
                  >
                    <span className="w-5 font-mono text-accent">+</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-muted">{docId}</span>
                    <span className="rounded border border-accent/40 px-2 py-0.5 font-mono text-[10px] text-accent">
                      backfilled
                    </span>
                  </li>
                ))
              : null}
          </ul>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-retired/30 bg-surface p-6">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-light tracking-[0.2em] text-faint uppercase">
              Baseline answer · model-judged {baselineCorrect === false ? "incorrect" : ""}
            </p>
            {baselineCorrect === false ? (
              <Icon name="cancel-circle" size={18} className="text-retired" />
            ) : null}
          </div>
          <p className="pt-3 text-sm leading-relaxed font-light text-muted">
            {baselineAnswer ?? "not generated"}
          </p>
        </div>
        <div className="rounded-lg border border-accent/30 bg-surface p-6">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-light tracking-[0.2em] text-faint uppercase">
              Temporal Cut answer · model-judged {canonCorrect ? "correct" : ""}
            </p>
            {canonCorrect ? <Icon name="checkmark-circle-02" size={18} className="text-accent" /> : null}
          </div>
          <p className="pt-3 text-sm leading-relaxed font-light text-muted">
            {canonAnswer ?? "not generated"}
          </p>
        </div>
      </section>

      <section className="flex flex-wrap items-center gap-6 rounded-lg border border-line bg-surface px-6 py-5">
        {response ? <StateBadge state={response.state} /> : null}
        <div className="font-mono text-xs text-muted">
          graph resolution:{" "}
          <span className={mode === "historical" ? "text-retired" : "text-accent"}>
            {response?.answer_value ?? "…"}
          </span>
          <span className="pl-3 text-faint">
            ({mode === "current" ? `retired ${oldValue}` : `current ${newValue}`})
          </span>
        </div>
        <span className="font-mono text-[10px] text-faint">
          retrieval {response?.retrieval_ms.toFixed(0) ?? "–"} ms · grounding{" "}
          {response?.grounding_ms.toFixed(0) ?? "–"} ms
          {judgeModel ? ` · answers judged by ${judgeModel}` : ""}
        </span>
      </section>
    </div>
  )
}
