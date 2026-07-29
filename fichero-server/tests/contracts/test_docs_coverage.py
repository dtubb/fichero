"""Docs drift guard for the committed public OpenAPI surface."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json"
DOCS_DIR = ROOT / "docs" / "contributor" / "api-reference"
ALLOWLIST = DOCS_DIR / "path_allowlist.json"


def _public_paths() -> set[str]:
    return set(json.loads(OPENAPI.read_text())["paths"].keys())


def _documented_paths() -> set[str]:
    text = "\n".join(
        path.read_text()
        for path in sorted(DOCS_DIR.glob("*.md"))
    )
    return {path for path in _public_paths() if path in text}


def _allowlisted_paths() -> dict[str, str]:
    payload = json.loads(ALLOWLIST.read_text())
    return payload.get("paths", {})


def test_every_public_openapi_path_is_documented_or_allowlisted() -> None:
    public = _public_paths()
    documented = _documented_paths()
    allowlisted = _allowlisted_paths()
    missing = sorted(public - documented - set(allowlisted))

    assert not missing, (
        f"{len(missing)} public OpenAPI path(s) are not mentioned in docs/contributor/api-reference/*.md "
        f"and not allowlisted in {ALLOWLIST.relative_to(ROOT)}:\n  " + "\n  ".join(missing)
    )

