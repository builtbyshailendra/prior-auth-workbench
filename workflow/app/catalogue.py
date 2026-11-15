"""The service catalogue: which services need authorization, and what documents each one needs.

The rules live in rules/catalogue.yaml, not in code, so the people who own them
(clinical policy, not engineering) can change them through a reviewed file, and
every case can record exactly which version it was checked against.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "rules" / "catalogue.yaml"


class CatalogueError(ValueError):
    """The catalogue file is malformed. Raised at startup, never mid-request."""


@dataclass(frozen=True)
class RequiredDocument:
    type: str
    label: str


@dataclass(frozen=True)
class Service:
    code: str
    name: str
    auth_required: bool
    required_documents: tuple[RequiredDocument, ...]
    facts: tuple[str, ...]


@dataclass(frozen=True)
class Catalogue:
    version: str
    services: dict[str, Service]

    def service(self, code: str) -> Service | None:
        return self.services.get(code)

    def needs_authorization(self, code: str) -> bool:
        """A code that isn't in the catalogue doesn't need authorization."""
        service = self.service(code)
        return bool(service and service.auth_required)

    def missing_documents(self, code: str, received_types: set[str]) -> list[RequiredDocument]:
        """Every required document that hasn't arrived, in checklist order."""
        service = self.service(code)
        if service is None:
            return []
        return [doc for doc in service.required_documents if doc.type not in received_types]


def load(path: Path = DEFAULT_PATH) -> Catalogue:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CatalogueError(f"Can't read the catalogue at {path}: {error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("version"), str) or not isinstance(raw.get("services"), dict):
        raise CatalogueError("The catalogue needs a string 'version' and a 'services' mapping")

    services: dict[str, Service] = {}
    for code, entry in raw["services"].items():
        code = str(code)
        if not isinstance(entry, dict):
            raise CatalogueError(f"Service {code}: expected a mapping")
        for key in ("name", "auth_required", "required_documents", "facts"):
            if key not in entry:
                raise CatalogueError(f"Service {code}: missing '{key}'")
        docs = []
        for doc in entry["required_documents"] or []:
            if not isinstance(doc, dict) or not doc.get("type") or not doc.get("label"):
                raise CatalogueError(f"Service {code}: each required document needs a type and a label")
            docs.append(RequiredDocument(type=str(doc["type"]), label=str(doc["label"])))
        if entry["auth_required"] is not True and docs:
            raise CatalogueError(f"Service {code}: a service without authorization can't require documents")
        services[code] = Service(
            code=code,
            name=str(entry["name"]),
            auth_required=entry["auth_required"] is True,
            required_documents=tuple(docs),
            facts=tuple(str(f) for f in entry["facts"] or []),
        )
    return Catalogue(version=raw["version"], services=services)
