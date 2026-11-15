"""The workflow service's HTTP API."""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import catalogue as catalogue_module
from app.db import SessionLocal, create_schema, get_session
from app.intake import CaseClosed, IntakeRejected, add_documents, receive
from app.models import Case
from app.schemas import DocumentsIn, IntakeRequest
from app.seed import load_members
from app.views import case_detail, case_summary

CATALOGUE = catalogue_module.load()


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    if os.environ.get("SEED_DEMO_DATA", "1") == "1":
        with SessionLocal() as session:
            load_members(session)
    yield


app = FastAPI(title="prior-auth-workbench workflow", lifespan=lifespan)


@app.middleware("http")
async def trace_ids(request: Request, call_next):
    """One trace ID per request: taken from the caller (connectors send one) or made here."""
    incoming = request.headers.get("x-trace-id", "")
    request.state.trace_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.get("/api/health")
def health() -> dict:
    """The process is up. No database call, so a database outage doesn't restart every copy."""
    return {"status": "ok"}


@app.get("/api/ready")
def ready(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "not ready", "detail": "Can't reach the database"}, status_code=503)
    return {"status": "ready"}


@app.get("/api/catalogue")
def get_catalogue() -> dict:
    return {
        "version": CATALOGUE.version,
        "services": [
            {"code": s.code, "name": s.name, "auth_required": s.auth_required,
             "required_documents": [{"type": d.type, "label": d.label} for d in s.required_documents]}
            for s in CATALOGUE.services.values()
        ],
    }


@app.post("/api/intake")
def intake(payload: IntakeRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    try:
        result = receive(session, payload, catalogue=CATALOGUE, actor=f"{payload.source}-connector", role="connector",
                         trace_id=request.state.trace_id)
    except IntakeRejected as rejected:
        return JSONResponse(
            {"detail": str(rejected), "problems": [p.__dict__ for p in rejected.problems]}, status_code=422
        )
    response.status_code = 201 if result.outcome == "created" else 200
    return {"outcome": result.outcome, "case": case_detail(session, result.case, CATALOGUE)}


@app.post("/api/cases/{case_id}/documents")
def post_documents(case_id: int, payload: DocumentsIn, request: Request, session: Session = Depends(get_session)):
    try:
        case = add_documents(session, case_id, payload.documents, catalogue=CATALOGUE, actor="intake-api",
                             role="connector", trace_id=request.state.trace_id)
    except CaseClosed as closed:
        raise HTTPException(409, str(closed)) from None
    if case is None:
        raise HTTPException(404, "No such case")
    return case_detail(session, case, CATALOGUE)


@app.get("/api/cases")
def list_cases(state: str | None = None, service: str | None = None, priority: str | None = None,
               session: Session = Depends(get_session)) -> list[dict]:
    """The queue: earliest deadline first, so at-risk cases are always at the top."""
    query = select(Case).order_by(Case.due_at, Case.id)
    if state:
        query = query.where(Case.state == state)
    if service:
        query = query.where(Case.service_code == service)
    if priority:
        query = query.where(Case.priority == priority)
    return [case_summary(c, CATALOGUE) for c in session.scalars(query.limit(200))]


@app.get("/api/cases/{case_id}")
def get_case(case_id: int, session: Session = Depends(get_session)) -> dict:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "No such case")
    return case_detail(session, case, CATALOGUE)
