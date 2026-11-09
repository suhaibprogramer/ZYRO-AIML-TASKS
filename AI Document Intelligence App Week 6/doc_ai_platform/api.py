"""REST API (FastAPI) for production-facing processing and integration.

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs  (interactive, generated from the models below)

Security: if the API_KEY environment variable is set, every endpoint except
/health requires the header  X-API-Key: <value>. Leave it empty only for local use.
"""
import hmac
import logging
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

import audit
import config
import database as db
import rag
import reports
import service
import storage
import workflow as wf

log = logging.getLogger("api")

app = FastAPI(title="AI Document Intelligence & Workflow Platform", version="1.0.0",
              description="Upload, process, review and query documents.")

# Upload / processing error codes -> HTTP status
HTTP_FOR_CODE = {"unsupported_type": 415, "too_large": 413, "empty": 422, "invalid_content": 422,
                 "corrupt": 422, "too_many_pages": 422, "too_large_image": 413, "duplicate": 409,
                 "ocr_unavailable": 503, "database": 503, "storage": 500, "path_denied": 400}


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    recovered = service.recover_interrupted()
    if recovered:
        log.info("Recovered %s interrupted document(s)", recovered)


def require_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Protects endpoints when API_KEY is configured."""
    if config.API_KEY and not hmac.compare_digest(x_api_key or "", config.API_KEY):
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")


# ------------------------------------------------------------------- models
class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500, description="Why the document is rejected")


class ApproveBody(BaseModel):
    note: str = Field(default="", max_length=500)


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def _public(doc: dict, detail: bool = False) -> dict:
    """The fields the API exposes. Stored file paths and raw text are never returned in lists."""
    out = {k: doc[k] for k in ("id", "filename", "doc_type", "status", "confidence", "classifier", "text_method",
                               "review_reason", "uploaded_at", "updated_at", "processing_ms")}
    out.update(fields=doc["fields"], validation=doc["validation"], anomalies=doc["anomalies"])
    if detail:
        out.update(timings_ms=doc["timings"], history=audit.get_history(doc["id"]),
                   text_preview=(doc.get("extracted_text") or "")[:1000])
    return out


def _or_404(doc_id: int) -> dict:
    doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    return doc


def _db_guard(fn, *args):
    try:
        return fn(*args)
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ---------------------------------------------------------------- endpoints
@app.get("/health", tags=["system"])
def health():
    """Liveness check (no key needed)."""
    try:
        return {"status": "ok", "documents": db.metrics()["total"]}
    except db.DatabaseError:
        raise HTTPException(status_code=503, detail="Database unavailable.")


@app.post("/documents", status_code=201, tags=["documents"], dependencies=[Depends(require_key)])
async def upload_document(file: UploadFile = File(...), process: bool = Query(True)):
    """Upload a PDF/PNG/JPG and (by default) run the full workflow."""
    data = await file.read(config.MAX_FILE_BYTES + 1)  # never read more than the limit + 1 byte
    res = service.upload_and_process(file.filename or "", data, process)
    up = res["upload"]
    if not up.ok:
        status = HTTP_FOR_CODE.get(up.code, 400)
        detail = {"message": up.message, "code": up.code}
        if up.duplicate_of:
            detail["existing_document_id"] = up.duplicate_of
        raise HTTPException(status_code=status, detail=detail)
    body = {"document": _public(_db_guard(db.get_document, up.doc_id), detail=True)}
    if res["workflow"]:
        body["workflow"] = res["workflow"]
    return body


@app.get("/documents", tags=["documents"], dependencies=[Depends(require_key)])
def list_documents(status: Optional[str] = None, type: Optional[str] = None, q: Optional[str] = None,
                   limit: int = Query(100, ge=1, le=500)):
    """List or search documents (filename, type, company, invoice number, name, email)."""
    if status and status != "All" and status not in wf.ALL_STATES:
        raise HTTPException(status_code=422, detail=f"status must be one of {wf.ALL_STATES}")
    docs = _db_guard(db.list_documents, status, q, type)[:limit]
    return {"count": len(docs), "documents": [_public(d) for d in docs]}


@app.get("/documents/{doc_id}", tags=["documents"], dependencies=[Depends(require_key)])
def get_document(doc_id: int):
    """One document with its fields, validation, anomalies, timings and audit history."""
    return _public(_or_404(doc_id), detail=True)


@app.post("/documents/{doc_id}/process", tags=["workflow"], dependencies=[Depends(require_key)])
def process_document(doc_id: int):
    """Run the workflow on a New document (already processed documents are skipped)."""
    _or_404(doc_id)
    return service.run_workflow(doc_id)


@app.post("/documents/{doc_id}/approve", tags=["workflow"], dependencies=[Depends(require_key)])
def approve_document(doc_id: int, body: ApproveBody = ApproveBody()):
    _or_404(doc_id)
    try:
        wf.approve(doc_id, body.note)
    except wf.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _public(_or_404(doc_id), detail=True)


@app.post("/documents/{doc_id}/reject", tags=["workflow"], dependencies=[Depends(require_key)])
def reject_document(doc_id: int, body: RejectBody):
    _or_404(doc_id)
    try:
        wf.reject(doc_id, body.reason)
    except wf.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _public(_or_404(doc_id), detail=True)


@app.post("/ask", tags=["assistant"], dependencies=[Depends(require_key)])
def ask(body: AskBody):
    """Ask a question answered only from the stored documents, with sources."""
    return _db_guard(rag.ask, body.question)


@app.get("/metrics", tags=["reports"], dependencies=[Depends(require_key)])
def metrics():
    return _db_guard(db.metrics)


@app.get("/reports/documents.csv", tags=["reports"], dependencies=[Depends(require_key)])
def documents_csv():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(_db_guard(reports.documents_csv), media_type="text/csv")
