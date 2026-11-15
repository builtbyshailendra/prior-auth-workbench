"""Sign-in and permissions.

People sign in with a username and password and get a signed session cookie.
Services (the connectors, the extraction worker) use API tokens. Every request
re-reads the user from the database, so deactivating someone takes effect at
once and a role change can't be dodged with an old cookie.

A real deployment would put this behind the client's identity provider (single
sign-on); see docs/decisions/0002-sign-in.md. The parts that stay the same are
the roles and the permission checks.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.clocks import clock
from app.db import get_session
from app.models import User

log = logging.getLogger("workflow.auth")

COOKIE = "pa_session"
SESSION_LENGTH = timedelta(hours=8)
MAX_FAILURES = 5
LOCKOUT = timedelta(minutes=15)
HUMAN_ROLES = ("intake_coordinator", "nurse_reviewer", "medical_director", "admin")
SERVICE_ACCOUNTS = {"CONNECTOR_TOKEN": ("connector", "connector"), "EXTRACTOR_TOKEN": ("extraction-worker", "extractor")}


def _secret() -> bytes:
    value = os.environ.get("SESSION_SECRET", "")
    if len(value) >= 32:
        return value.encode()
    if os.environ.get("APP_ENV", "dev") == "dev":
        # Local development only: a random secret per process, so sessions end on restart.
        global _DEV_SECRET
        if _DEV_SECRET is None:
            log.warning("SESSION_SECRET not set; using a random one for this process (dev only)")
            _DEV_SECRET = secrets.token_bytes(32)
        return _DEV_SECRET
    raise RuntimeError("SESSION_SECRET must be set (at least 32 characters) outside development")


_DEV_SECRET: bytes | None = None


# --- passwords ---------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# --- session tokens ----------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_session_token(username: str) -> str:
    payload = _b64(json.dumps({"u": username, "exp": int((clock.now() + SESSION_LENGTH).timestamp())}).encode())
    signature = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def read_session_token(token: str) -> str | None:
    """The username in a valid, unexpired token, or None."""
    try:
        payload, signature = token.split(".")
        expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) <= clock.now().timestamp():
        return None
    return data.get("u")


# --- who is calling ----------------------------------------------------------------

@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    display_name: str
    kind: str  # "user" or "service"


def _service_principal(token: str) -> Principal | None:
    for env, (name, role) in SERVICE_ACCOUNTS.items():
        expected = os.environ.get(env, "")
        if len(expected) >= 24 and hmac.compare_digest(token.encode(), expected.encode()):
            return Principal(name, role, name, "service")
    return None


def current_principal(request: Request, session: Session = Depends(get_session)) -> Principal:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        principal = _service_principal(authorization.removeprefix("Bearer ").strip())
        if principal is None:
            raise HTTPException(401, "Invalid API token")
        return principal

    username = read_session_token(request.cookies.get(COOKIE, ""))
    if username is None:
        raise HTTPException(401, "Sign in first")
    user = session.get(User, username)
    if user is None or not user.active:
        raise HTTPException(401, "Sign in first")
    # A cookie can't be sent with a custom header from another site, so this blocks cross-site form posts.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "workbench":
        raise HTTPException(403, "Missing X-Requested-With header")
    return Principal(user.username, user.role, user.display_name, "user")


def require(*roles: str):
    def check(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(403, f"{principal.display_name} can't do this as {principal.role.replace('_', ' ')}.")
        return principal

    return check


# --- signing in --------------------------------------------------------------------

class SignInFailed(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def sign_in(session: Session, username: str, password: str) -> User:
    """Check a password. Five wrong attempts lock the account for 15 minutes."""
    user = session.get(User, username, with_for_update=True)
    now = clock.now()
    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise SignInFailed("Too many failed attempts. Try again in 15 minutes.", 429)
    if user is None or not user.active or not verify_password(password, user.password_hash):
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILURES:
                user.locked_until = now + LOCKOUT
                user.failed_logins = 0
            session.commit()
        raise SignInFailed("Wrong username or password")
    user.failed_logins = 0
    user.locked_until = None
    session.commit()
    return user
