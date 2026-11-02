"""One model per role from the rules file (dev-workflows.models.by-config): `harness.toml` [models] names, per role,
a provider and a model; a role whose provider is not in [models].providers is a Question for a person, never a
silent fallback. A role changes model only by someone editing the file. Imports nothing from the engine."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROLES = ("builder", "reviewer", "spec-writer", "helper", "researcher", "manager")  # manager: reads and answers the loop's alerts


class Question(Exception):
    """Something a person must answer before the role can run."""


@dataclass(frozen=True)
class Model:
    provider: str
    model: str
    context: int = 200_000


def load(root) -> dict:
    f = Path(root) / "harness.toml"
    return tomllib.loads(f.read_text()).get("models", {}) if f.is_file() else {}


def for_role(cfg: dict, role: str) -> Model:
    """The role's Model; a Question names what is missing (role, provider, or a provider nobody set up)."""
    row = cfg.get(role)
    if not isinstance(row, dict) or not row.get("provider") or not row.get("model"):
        raise Question(f"harness.toml [models].{role} must name a provider and a model")
    known = cfg.get("providers") or []
    if row["provider"] not in known:
        raise Question(f"harness.toml [models].{role} uses provider {row['provider']!r}, not among providers {known}: set it up or change the role")
    return Model(row["provider"], row["model"], int(row.get("context", Model.context)))
