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

  const [showProof, setShowProof] = useState(false)
  const kept = response?.documents.filter((d) => d.kept) ?? []
  const backfill = response?.backfill_doc_ids ?? []
  const cutDoc = response?.documents.find(
    (d) => d.disposition === "superseded_for_current_grounding",
  )
  const retiredSpan =
    cutDoc?.evidence_span ??
    response?.evidence.find((row) => row.doc_id === cutDoc?.doc_id)?.evidence_span ??
    null
  const supersedingSpan = response?.evidence[0]?.evidence_span ?? null
  const supersedingDocId = response?.evidence[0]?.doc_id ?? null
  const supersessionQuery = response?.query_cards.find((card) =>
    card.query_name.includes("event"),
  )

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
              Plain retrieval
            </p>
            {baselineCorrect === false ? (
              <span className="flex items-center gap-2 font-mono text-[10px] tracking-[0.14em] text-retired uppercase">
                model-judged incorrect
                <Icon name="cancel-circle" size={18} className="text-retired" />
              </span>
            ) : null}
          </div>
          <p className="pt-4 text-[10px] font-light tracking-[0.2em] text-faint uppercase">
            Value left in its context
          </p>
          <p className="pt-1 font-mono text-2xl font-light text-retired line-through decoration-retired/40">
            {oldValue}
          </p>
          <p className="pt-4 text-sm leading-relaxed font-light text-muted">
            {baselineAnswer ?? "not generated"}
          </p>
        </div>
        <div className="rounded-lg border border-accent/30 bg-surface p-6">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-light tracking-[0.2em] text-faint uppercase">
              Temporal Cut
            </p>
            {canonCorrect ? (
              <span className="flex items-center gap-2 font-mono text-[10px] tracking-[0.14em] text-accent uppercase">
                model-judged correct
                <Icon name="checkmark-circle-02" size={18} className="text-accent" />
              </span>
            ) : null}
          </div>
          <p className="pt-4 text-[10px] font-light tracking-[0.2em] text-faint uppercase">
            Value left in its context
          </p>
          <p className="pt-1 font-mono text-2xl font-light text-accent">{newValue}</p>
          <p className="pt-4 text-sm leading-relaxed font-light text-muted">
            {canonAnswer ?? "not generated"}
          </p>
        </div>
      </section>

      <p className="text-center font-mono text-[11px] tracking-[0.16em] text-faint uppercase">
        Same BM25 · same model · same prompt · same 10-document budget
      </p>

      <section className="rounded-lg border border-line bg-surface">
        <button
          type="button"
          onClick={() => setShowProof((open) => !open)}
          className="flex w-full items-center justify-between px-6 py-5 text-left"
        >
          <span className="text-sm font-light text-ink">Why was this cut?</span>
          <Icon
            name={showProof ? "arrow-up-01" : "arrow-down-01"}
            size={18}
            className="text-faint"
          />
        </button>
        {showProof ? (
          <div className="grid gap-6 border-t border-line px-6 py-6 lg:grid-cols-2">
            <div className="flex flex-col gap-5">
              <div>
                <p className="text-[10px] font-light tracking-[0.2em] text-retired uppercase">
                  Retired evidence · {cutDoc?.doc_id ?? "none"}
                </p>
                <p className="pt-2 font-mono text-[11px] leading-relaxed text-muted">
                  {retiredSpan ? `“${retiredSpan}”` : "—"}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-light tracking-[0.2em] text-accent uppercase">
                  Superseding evidence · {supersedingDocId ?? "none"}
                </p>
                <p className="pt-2 font-mono text-[11px] leading-relaxed text-muted">
                  {supersedingSpan ? `“${supersedingSpan}”` : "—"}
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-5">
              <div>
                <p className="text-[10px] font-light tracking-[0.2em] text-faint uppercase">
                  HydraDB path
                </p>
                <div className="pt-2 font-mono text-[11px] leading-relaxed text-muted">
                  <p>ClaimKey {response?.claim_key ?? "—"}</p>
                  <p className="pl-4 text-retired">└─ Proposition {oldValue} · retired</p>
                  <p className="pl-4">
                    └─ CanonEvent {response?.transition ?? "—"} ·{" "}
                    {response?.temporal_quality ?? "—"}
                  </p>
                  <p className="pl-4 text-accent">└─ Proposition {newValue} · current</p>
                </div>
              </div>
              <div>
                <p className="text-[10px] font-light tracking-[0.2em] text-faint uppercase">
                  Proof
                </p>
                <p className="pt-2 font-mono text-[11px] leading-relaxed text-muted">
                  {response?.query_cards.length ?? 0} HydraDB queries ·{" "}
                  {response?.grounding_ms.toFixed(0) ?? "–"} ms
                </p>
                <p className="pt-1 font-mono text-[10px] break-all text-faint">
                  {supersessionQuery
                    ? `${supersessionQuery.query_name} · ${supersessionQuery.query_id}`
                    : ""}
                </p>
              </div>
            </div>
          </div>
        ) : null}
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
