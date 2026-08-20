export const API = process.env.CANON_API ?? "http://127.0.0.1:8000"

export type TruthState = "CANON" | "CONTESTED" | "UNKNOWN"
export type TemporalQuality = "T1" | "T2" | "T3"

export type Dashboard = {
  corpus_documents: number
  claim_keys: number
  current_conflicts: number
  contested_claims: number
  verified_residue: number
  derived_residue: number
  lexical_restatement_residue: number
  verified_resurrections: number
  resurrection_note: string
  graph_counts: Record<string, number>
}

export type ConflictSummary = {
  question_id: string
  claim_key: string
  entity: string
  predicate: string
  state: TruthState
  current_value: string | null
  retired_values: string[]
  transition: string
  temporal_quality: TemporalQuality
  verified_structured_residue: number
  derived_free_text_residue: number
  lexical_restatement_residue: number
}

export type Evidence = {
  doc_id: string
  discovery: string
  source_type: string
  title: string
  evidence_span: string
  stance: string
  structured: boolean
  source_field: string | null
  asserted_at: string | null
  residue_class: string | null
}

export type CanonEvent = {
  id: number
  selects_value: string
  supersedes_event_id: number | null
  transition: string
  temporal_quality: TemporalQuality
  evidence_doc_id: string
  occurred_at: string | null
}

export type QueryCard = {
  engine: string
  operation: string
  query_name: string
  cypher: string
  parameters: Record<string, unknown>
  result_count: number
  client_round_trip_ms: number
  query_id: string
  engine_rows_duration_us: number | null
  engine_ops_observed: number | null
}

export type TruthChange = {
  question_id: string
  claim_key: string
  entity: string
  predicate: string
  state: TruthState
  current_value: string | null
  retired_values: string[]
  contested_values: string[]
  transition: string
  temporal_quality: TemporalQuality
  events: CanonEvent[]
  current_evidence: Evidence[]
  retired_evidence: Evidence[]
  residue: Evidence[]
  query_cards: QueryCard[]
}

export type GroundedDoc = {
  doc_id: string
  source_type: string
  title: string
  disposition: string
  rank: number | null
  kept: boolean
}

export type AskResponse = {
  question: string
  mode: string
  state: TruthState
  answer_value: string | null
  why: string
  claim_key: string | null
  temporal_quality: TemporalQuality | null
  transition: string | null
  evidence: Evidence[]
  retired_evidence_filtered: number
  documents: GroundedDoc[]
  backfill_doc_ids: string[]
  query_cards: QueryCard[]
  retrieval_ms: number
  grounding_ms: number
}

export type ResidueRow = {
  question_id: string
  claim_key: string
  entity: string
  retired_value: string
  current_value: string | null
  residue_class: string
  discovery: string
  doc_id: string
  source_type: string
  title: string
  evidence_span: string
  source_field: string | null
}

export type ResidueReport = {
  definition: Record<string, string>
  counts: Record<string, number>
  rows: ResidueRow[]
}

export type Alias = {
  value: string
  alias_type: string
  resolution: string
  support: number
  candidate_count: number
  candidates: Array<{ name: string; organization: string }>
  evidence_doc_id: string
  evidence_span: string
}

export type IdentityReport = {
  definition: Record<string, string>
  corpus: Record<string, number>
  materialised: Record<string, number>
  note: string
  aliases: Alias[]
}

export type ArmVerdict = {
  satisfied_facts: number
  total_facts: number
  states_current_value: boolean
  presents_retired_as_current: boolean
  abstains: boolean
  judge_model: string
  unanimous: boolean
}

export type ConflictArm = {
  arm: string
  doc_ids: string[]
  answer: string | null
  verdict: ArmVerdict | null
}

export type ConflictRun = {
  question_id: string
  question: string
  old_value: string
  new_value: string
  dropped_doc_ids: string[]
  baseline: ConflictArm
  canon_filtered: ConflictArm
  canon: ConflictArm
}

export type Results = {
  measured_at: string
  corpus_documents: number
  top_k: number
  answer_model: string | null
  not_run: string[]
  summary: Record<string, number>
  question_ids: Record<string, string[]>
  conflicts: ConflictRun[]
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store" })
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`)
  }
  return (await response.json()) as T
}

export const getDashboard = () => get<Dashboard>("/dashboard")
export const getConflicts = () => get<ConflictSummary[]>("/conflicts")
export const getConflict = (id: string) => get<TruthChange>(`/conflicts/${id}`)
export type OfficialArm = {
  label: string
  questions_scored: number
  correctness_pct: number
  completeness_pct: number
  combined_score: number
  document_recall_pct: number
  invalid_extra_docs: number
  by_question_type: Record<string, { correct: number; total: number }>
}

export type OfficialEval = {
  harness: string
  harness_repo: string
  judge_model: string
  measured_at: string
  arms: Record<string, OfficialArm>
}

export const getOfficial = () =>
  get<OfficialEval>("/official").catch(() => null)

export const getResults = () => get<Results>("/results")
export const getResidue = () => get<ResidueReport>("/residue")
export const getEntities = () => get<IdentityReport>("/entities")

export async function ask(question: string, mode: string, topK = 10): Promise<AskResponse> {
  const response = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode, top_k: topK }),
  })
  if (!response.ok) {
    throw new Error(`ask failed with ${response.status}`)
  }
  return (await response.json()) as AskResponse
}
