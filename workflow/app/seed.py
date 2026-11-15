"""Loads the synthetic member list: this project's stand-in for the core admin system."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Coverage, Member, User

MEMBERS_FILE = Path(__file__).resolve().parent.parent / "seed" / "members.json"
USERS_FILE = Path(__file__).resolve().parent.parent / "seed" / "users.json"


def load_members(session: Session, path: Path = MEMBERS_FILE) -> int:
    """Insert the members if the table is empty. Returns how many were added."""
    if session.scalar(select(func.count()).select_from(Member)):
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    for m in data["members"]:
        session.add(Member(id=m["id"], name=m["name"], birth_date=date.fromisoformat(m["birth_date"])))
    # No ORM relationship links the two, so save members before the coverage rows that point at them.
    session.flush()
    for m in data["members"]:
        for c in m["coverage"]:
            session.add(Coverage(
                member_id=m["id"],
                plan=c["plan"],
                start=date.fromisoformat(c["start"]),
                end=date.fromisoformat(c["end"]) if c["end"] else None,
            ))
    session.commit()
    return len(data["members"])


def load_users(session: Session, password: str, path: Path = USERS_FILE) -> int:
    """Create the demo staff accounts that don't exist yet, all with the given password."""
    added = 0
    for u in json.loads(path.read_text(encoding="utf-8"))["users"]:
        if session.get(User, u["username"]) is None:
            session.add(User(username=u["username"], display_name=u["display_name"], role=u["role"],
                             password_hash=hash_password(password)))
            added += 1
    session.commit()
    return added
