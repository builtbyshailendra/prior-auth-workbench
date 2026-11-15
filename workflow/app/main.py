"""The workflow service's HTTP API."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import catalogue as catalogue_module
from app.auth import (
    COOKIE,
    HUMAN_ROLES,
    SESSION_LENGTH,
    Principal,
    SignInFailed,
    current_principal,
    hash_password,
    make_session_token,
    require,
    sign_in,
)
from app.db import SessionLocal, create_schema, get_session
from app.extraction import service as extraction
from app.intake import CaseClosed, IntakeRejected, add_documents, open_rfi, receive
from app.lifecycle import REASON_CODES, Invalid, NotAllowed, WrongState, can_view, take, visible_to
from app.models import Case, Document, User
from app.schemas import ClaimIn, DocumentsIn, ExtractionResultIn, IntakeRequest
from app.seed import load_members, load_users
from app.views import case_detail, case_summary

CATALOGUE = catalogue_module.load()
DEV = os.environ.get("APP_ENV", "dev") == "dev"
log = logging.getLogger("workflow")


async def sweep_forever() -> None:
    """Every 30 seconds, send cases whose extraction never came back to manual entry."""
    while True:
        await asyncio.sleep(30)
        try:
            with SessionLocal() as session:
                moved = extraction.sweep(session)
            if moved:
                log.warning("extraction sweep moved %s case(s) to manual entry", moved)
        except Exception:  # never let the sweep kill the service
            log.exception("extraction sweep failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    if os.environ.get("SEED_DEMO_DATA", "1") == "1":
        with SessionLocal() as session:
            load_members(session)
            password = os.environ.get("DEMO_PASSWORD") or ("demo-password" if DEV else "")
            if password:
                load_users(session, password)
    sweeper = asyncio.create_task(sweep_forever()) if extraction.mode() == "worker" else None
    yield
    if sweeper:
        sweeper.cancel()


app = FastAPI(title="prior-auth-workbench workflow", lifespan=lifespan)


@app.middleware("http")
async def trace_ids(request: Request, call_next):
    """One trace ID per request: taken from the caller (connectors send one) or made here."""
    incoming = request.headers.get("x-trace-id", "")
    request.state.trace_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


# --- health ------------------------------------------------------------------------

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


# --- signing in --------------------------------------------------------------------

class SignIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


def me_view(user: User | Principal) -> dict:
    return {"username": user.username, "display_name": user.display_name, "role": user.role}


@app.post("/api/auth/login")
def login(payload: SignIn, response: Response, session: Session = Depends(get_session)):
    try:
        user = sign_in(session, payload.username, payload.password)
    except SignInFailed as failed:
        return JSONResponse({"detail": str(failed)}, status_code=failed.status)
    response.set_cookie(COOKIE, make_session_token(user.username), max_age=int(SESSION_LENGTH.total_seconds()),
                        httponly=True, samesite="strict", secure=not DEV, path="/")
    return me_view(user)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"status": "signed out"}


@app.get("/api/auth/me")
def me(principal: Principal = Depends(current_principal)) -> dict:
    return me_view(principal)


# --- reference data ----------------------------------------------------------------

@app.get("/api/catalogue")
def get_catalogue(_: Principal = Depends(current_principal)) -> dict:
    return {
        "version": CATALOGUE.version,
        "services": [
            {"code": s.code, "name": s.name, "auth_required": s.auth_required,
             "required_documents": [{"type": d.type, "label": d.label} for d in s.required_documents]}
            for s in CATALOGUE.services.values()
        ],
    }


@app.get("/api/reason-codes")
def reason_codes(_: Principal = Depends(current_principal)) -> list[dict]:
    return [{"code": code, "label": label} for code, label in REASON_CODES.items()]


# --- intake ------------------------------------------------------------------------

def compact(case: Case, outcome: str) -> dict:
    """What a connector gets back: enough to log and route, no clinical detail."""
    rfi = open_rfi(case)
    return {"outcome": outcome, "case_id": case.id, "state": case.state, "due_at": case.due_at.isoformat(),
            "missing": [m["type"] for m in rfi.items] if rfi else []}


@app.post("/api/intake")
def intake(payload: IntakeRequest, request: Request, response: Response, session: Session = Depends(get_session),
           principal: Principal = Depends(require("connector", "intake_coordinator"))):
    actor = f"{payload.source}-connector" if principal.kind == "service" else principal.username
    try:
        result = receive(session, payload, catalogue=CATALOGUE, actor=actor, role=principal.role,
                         trace_id=request.state.trace_id, on_complete=extraction.complete_case)
    except IntakeRejected as rejected:
        return JSONResponse({"detail": str(rejected), "problems": [p.__dict__ for p in rejected.problems]},
                            status_code=422)
    response.status_code = 201 if result.outcome == "created" else 200
    return compact(result.case, result.outcome)


@app.post("/api/cases/{case_id}/documents")
def post_documents(case_id: int, payload: DocumentsIn, request: Request, session: Session = Depends(get_session),
                   principal: Principal = Depends(require("connector", "intake_coordinator"))):
    try:
        case = add_documents(session, case_id, payload.documents, catalogue=CATALOGUE, actor=principal.username,
                             role=principal.role, trace_id=request.state.trace_id,
                             on_complete=extraction.complete_case)
    except CaseClosed as closed:
        raise HTTPException(409, str(closed)) from None
    if case is None:
        raise HTTPException(404, "No such case")
    return compact(case, "documents_added")


# --- cases -------------------------------------------------------------------------

def visible_case(session: Session, case_id: int, principal: Principal, *, lock: bool = False) -> Case:
    case = session.get(Case, case_id, with_for_update=lock)
    # Same answer for "doesn't exist" and "not yours", so case numbers don't leak.
    if case is None or not can_view(case, principal.role, principal.username):
        raise HTTPException(404, "No such case")
    return case


@app.get("/api/cases")
def list_cases(state: str | None = None, service: str | None = None, priority: str | None = None,
               session: Session = Depends(get_session),
               principal: Principal = Depends(require("intake_coordinator", "nurse_reviewer", "medical_director"))):
    """This person's queue: earliest deadline first, so at-risk cases are always at the top."""
    query = select(Case).where(visible_to(principal.role, principal.username)).order_by(Case.due_at, Case.id)
    if state:
        query = query.where(Case.state == state)
    if service:
        query = query.where(Case.service_code == service)
    if priority:
        query = query.where(Case.priority == priority)
    return [case_summary(c, CATALOGUE) for c in session.scalars(query.limit(200))]


@app.get("/api/cases/{case_id}")
def get_case(case_id: int, session: Session = Depends(get_session),
             principal: Principal = Depends(require("intake_coordinator", "nurse_reviewer", "medical_director"))):
    return case_detail(session, visible_case(session, case_id, principal), CATALOGUE)


@app.get("/api/cases/{case_id}/documents/{document_id}")
def get_document(case_id: int, document_id: int, session: Session = Depends(get_session),
                 principal: Principal = Depends(require("intake_coordinator", "nurse_reviewer", "medical_director"))):
    visible_case(session, case_id, principal)
    doc = session.get(Document, document_id)
    if doc is None or doc.case_id != case_id:
        raise HTTPException(404, "No such document")
    return {"id": doc.id, "doc_type": doc.doc_type, "title": doc.title, "text": doc.text}


class ActionIn(BaseModel):
    note: str = Field(default="", max_length=4000)
    reason_code: str | None = Field(default=None, max_length=40)


@app.post("/api/cases/{case_id}/{action}")
def act(case_id: int, action: Literal["start_review", "approve", "escalate", "deny", "withdraw"], payload: ActionIn,
        request: Request, session: Session = Depends(get_session),
        principal: Principal = Depends(require(*HUMAN_ROLES, "connector", "extractor"))):
    """People decide. The services' roles appear in no action's allowed list, so they always get 403."""
    case = session.get(Case, case_id, with_for_update=True)
    if case is None or (principal.kind == "user" and not can_view(case, principal.role, principal.username)):
        raise HTTPException(404, "No such case")
    try:
        take(session, case, action, user=principal.username, role=principal.role, trace_id=request.state.trace_id,
             note=payload.note, reason_code=payload.reason_code)
    except NotAllowed as refused:
        session.rollback()
        raise HTTPException(403, str(refused)) from None
    except WrongState as wrong:
        session.rollback()
        raise HTTPException(409, str(wrong)) from None
    except Invalid as invalid:
        session.rollback()
        raise HTTPException(422, str(invalid)) from None
    session.commit()
    return case_detail(session, case, CATALOGUE)


# --- extraction (the worker's two endpoints) -------------------------------------------

@app.post("/api/extraction/claim")
def claim_extraction(payload: ClaimIn, session: Session = Depends(get_session),
                     _: Principal = Depends(require("extractor"))) -> list[dict]:
    """Hand the worker cases waiting for extraction, with their documents. Each is leased for 5 minutes."""
    return [extraction.job(case, CATALOGUE) for case in extraction.claim(session, payload.limit)]


@app.post("/api/extraction/{case_id}")
def post_extraction(case_id: int, payload: ExtractionResultIn, request: Request, session: Session = Depends(get_session),
                    _: Principal = Depends(require("extractor"))) -> dict:
    """The worker's raw answers. Checked here against the documents; the worker is never trusted."""
    try:
        case = extraction.record_result(session, case_id, payload, CATALOGUE, request.state.trace_id)
    except WrongState as wrong:
        raise HTTPException(409, str(wrong)) from None
    if case is None:
        raise HTTPException(404, "No such case")
    return {"case_id": case.id, "state": case.state, "extraction_status": case.extraction_status,
            "facts": [{"field": f.field, "status": f.status} for f in case.facts]}


# --- users (admin only) --------------------------------------------------------------

class NewUser(BaseModel):
    username: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    role: Literal["intake_coordinator", "nurse_reviewer", "medical_director", "admin"]
    password: str = Field(min_length=12, max_length=200)


@app.get("/api/users")
def list_users(session: Session = Depends(get_session), _: Principal = Depends(require("admin"))) -> list[dict]:
    return [{**me_view(u), "active": u.active} for u in session.scalars(select(User).order_by(User.username))]


@app.post("/api/users", status_code=201)
def create_user(payload: NewUser, session: Session = Depends(get_session), _: Principal = Depends(require("admin"))):
    if session.get(User, payload.username) is not None:
        raise HTTPException(409, f"User {payload.username} already exists")
    user = User(username=payload.username, display_name=payload.display_name, role=payload.role,
                password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    return {**me_view(user), "active": True}


@app.post("/api/users/{username}/deactivate")
def deactivate_user(username: str, session: Session = Depends(get_session),
                    principal: Principal = Depends(require("admin"))):
    if username == principal.username:
        raise HTTPException(409, "You can't deactivate your own account")
    user = session.get(User, username)
    if user is None:
        raise HTTPException(404, "No such user")
    user.active = False
    session.commit()
    return {**me_view(user), "active": False}
