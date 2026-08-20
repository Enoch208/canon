import hashlib
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from canon_api.models import (
    AskRequest,
    AskResponse,
    ConflictSummaryModel,
    CutReasonModel,
    DashboardModel,
    GroundResponse,
    IdentityReportModel,
    OfficialEvalModel,
    ResidueReportModel,
    TruthChangeModel,
)
from canon_api.service import CanonService

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "eval" / "results" / "latest.json"


def warm_caches() -> None:
    if not service.healthy():
        return
    for build in (
        service.dashboard,
        service.conflicts,
        service.residue_report,
        service.identity_report,
    ):
        try:
            build()
        except Exception:
            return


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=warm_caches, daemon=True).start()
    yield


app = FastAPI(title="Canon", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
service = CanonService(ROOT)


@app.get("/health")
def health() -> dict[str, object]:
    return {"hydra": service.healthy(), "corpus_documents": service.store.count()}


@app.get("/dashboard")
def dashboard() -> DashboardModel:
    return service.dashboard()


@app.get("/conflicts")
def conflicts() -> list[ConflictSummaryModel]:
    return service.conflicts()


@app.get("/conflicts/{question_id}")
def conflict(question_id: str) -> TruthChangeModel:
    change = service.truth_change(question_id)
    if change is None:
        raise HTTPException(status_code=404, detail=f"no claim graph for {question_id}")
    return change


@app.get("/entities")
def entities() -> IdentityReportModel:
    return service.identity_report()


@app.get("/residue")
def residue() -> ResidueReportModel:
    return service.residue_report()


@app.post("/ask")
def ask(request: AskRequest) -> AskResponse:
    return service.ask(request.question, request.mode, request.top_k)


@app.post("/v1/ground")
def ground_endpoint(request: AskRequest) -> GroundResponse:
    if not service.healthy():
        raise HTTPException(
            status_code=503,
            detail={
                "state": "TEMPORAL_GRAPH_UNAVAILABLE",
                "reason": (
                    "HydraDB is unreachable, so Canon cannot decide which evidence is "
                    "currently valid. Refusing to ground rather than silently degrading "
                    "to plain retrieval."
                ),
            },
        )
    ask = service.ask(request.question, request.mode, request.top_k)
    ranked = sorted((d for d in ask.documents if d.rank is not None), key=lambda d: d.rank)
    suppressed = [
        d.doc_id for d in ask.documents if d.disposition == "superseded_for_current_grounding"
    ]
    spans = {row.doc_id: row.evidence_span for row in ask.evidence}
    final_context = [d.doc_id for d in ask.documents if d.kept] + ask.backfill_doc_ids
    return GroundResponse(
        state=ask.state,
        mode=ask.mode,
        answer_value=ask.answer_value,
        why=ask.why,
        input_ranking=[d.doc_id for d in ranked],
        current_evidence=[d.doc_id for d in ask.documents if d.disposition == "current_evidence"],
        suppressed_evidence=suppressed,
        historical_evidence=[
            d.doc_id for d in ask.documents if d.disposition == "historical_evidence"
        ],
        backfill_evidence=ask.backfill_doc_ids,
        cut=[
            CutReasonModel(
                doc_id=doc_id,
                claim_key=ask.claim_key,
                transition=ask.transition,
                temporal_quality=ask.temporal_quality,
                evidence_span=spans.get(doc_id),
            )
            for doc_id in suppressed
        ],
        final_context=final_context,
        context_sha256=hashlib.sha256("\n".join(final_context).encode()).hexdigest(),
        hydra_query_ids=[card.query_id for card in ask.query_cards],
        proof=ask.query_cards,
        retrieval_ms=ask.retrieval_ms,
        grounding_ms=ask.grounding_ms,
    )


@app.get("/official")
def official() -> OfficialEvalModel:
    payload = service.official_eval()
    if payload is None:
        raise HTTPException(status_code=404, detail="official evaluation not run")
    return payload


@app.get("/results")
def results() -> dict[str, object]:
    if not RESULTS.exists():
        raise HTTPException(status_code=404, detail="run `make benchmark` first")
    payload = json.loads(RESULTS.read_text())
    return {
        "measured_at": payload["measured_at"],
        "corpus_documents": payload["corpus_documents"],
        "top_k": payload["top_k"],
        "answer_model": payload["answer_model"],
        "not_run": payload["not_run"],
        "summary": payload["summary"],
        "question_ids": payload["question_ids"],
        "conflicts": [
            {
                "question_id": conflict["question_id"],
                "question": conflict["question"],
                "old_value": conflict["old_value"],
                "new_value": conflict["new_value"],
                "dropped_doc_ids": conflict["dropped_doc_ids"],
                **{
                    arm: {
                        "arm": conflict[arm]["arm"],
                        "doc_ids": conflict[arm]["doc_ids"],
                        "answer": conflict[arm]["answer"],
                        "verdict": conflict[arm].get("verdict"),
                    }
                    for arm in ("baseline", "canon_filtered", "canon")
                },
            }
            for conflict in payload["conflicts"]
        ],
    }
