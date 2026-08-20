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
    DashboardModel,
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
    }
