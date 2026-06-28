"""Unit tests for scripts/check_generated_wrapper_drift.py (#2660)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_generated_wrapper_drift.py"
_SPEC = importlib.util.spec_from_file_location("check_generated_wrapper_drift", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

idiomatic = _mod.idiomatic
expected_names = _mod.expected_names
violations = _mod.violations


def test_idiomatic_regression_2660():
    # The exact rename that broke the Release build on 2026-06-26.
    assert (
        idiomatic("fichero__knowledge__knowledge_models__EntityType")
        == "FicheroKnowledgeKnowledgeModelsEntityType"
    )
    assert idiomatic("fichero__knowledge_models__EntityType") == "FicheroKnowledgeModelsEntityType"


def test_idiomatic_identity_on_camelcase():
    assert idiomatic("APIKeyRequest") == "APIKeyRequest"
    assert idiomatic("ActivityResponse") == "ActivityResponse"
    assert idiomatic("_EmbedClaimRequest") == "EmbedClaimRequest"


def _spec(tmp_path: Path, schemas: dict) -> Path:
    p = tmp_path / "openapi.json"
    p.write_text(json.dumps({"components": {"schemas": {k: {} for k in schemas}}}))
    return p


def _wrapper(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body)
    return tmp_path / name


def test_flags_unresolved_reference(tmp_path):
    spec = _spec(tmp_path, {"fichero__knowledge__knowledge_models__EntityType": {}})
    _wrapper(
        tmp_path,
        "FooGenerated.swift",
        "let x = Components.Schemas.FicheroKnowledgeModelsEntityType.self\n",  # stale name
    )
    bad = violations(wrappers_dir=tmp_path, openapi_json=spec)
    assert bad, "reference to a renamed-away schema must be flagged"


def test_accepts_resolved_reference(tmp_path):
    spec = _spec(tmp_path, {"fichero__knowledge__knowledge_models__EntityType": {}})
    _wrapper(
        tmp_path,
        "FooGenerated.swift",
        "let x = Components.Schemas.FicheroKnowledgeKnowledgeModelsEntityType.self\n",
    )
    assert not violations(wrappers_dir=tmp_path, openapi_json=spec)


def test_nested_member_access_uses_toplevel(tmp_path):
    spec = _spec(tmp_path, {"ArtifactResponse": {}})
    _wrapper(
        tmp_path,
        "FooGenerated.swift",
        "let p: Components.Schemas.ArtifactResponse.PayloadPath = .init()\n",
    )
    assert not violations(wrappers_dir=tmp_path, openapi_json=spec)


def test_real_tree_clean():
    assert not violations(), "shipped wrappers must all resolve against openapi.json"
