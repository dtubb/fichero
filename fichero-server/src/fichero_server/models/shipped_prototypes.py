"""Prototypes that ship with the app as JSON (``resources/prototypes/*.json``), loaded as built-ins on open."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parents[1] / "resources" / "prototypes"


def shipped_prototypes() -> list[dict[str, Any]]:
    """Every shipped prototype, parents before children (so a save in this order always finds its parent)."""
    found = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(_DIR.glob("*.json"))]
    by_key = {p["key"]: p for p in found}
    ordered: list[dict[str, Any]] = []

    def add(proto: dict[str, Any]) -> None:
        if proto in ordered:
            return
        parent = by_key.get(proto.get("parent_key") or "")
        if parent:
            add(parent)
        ordered.append(proto)

    for proto in found:
        add(proto)
    return ordered
