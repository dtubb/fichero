"""Prove `check_artifact_type_contract` can FAIL, and on the right thing (#4420).

The check compares artifact type strings the Python server writes against the
strings the Swift client asks for. It exists because #4418 shipped a producer
writing "text_geometry" and a consumer querying "transcription" — two green
commits, one dead feature, found by a human reading both files side by side.

These tests pin the extraction on synthetic trees, so a regression fails here
rather than being discovered by the next dead feature.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_artifact_type_contract.py"
)


@pytest.fixture(scope="module")
def mod():
    assert _SCRIPT.exists(), f"{_SCRIPT} is missing — the check was deleted, not moved"
    spec = importlib.util.spec_from_file_location("cat_contract", _SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _py(tmp: Path, body: str) -> Path:
    root = tmp / "srv"
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod.py").write_text(body)
    return root


def _swift(tmp: Path, body: str) -> Path:
    root = tmp / "app"
    root.mkdir(parents=True, exist_ok=True)
    (root / "View.swift").write_text(body)
    return root


def test_producer_literal_is_extracted(mod, tmp_path):
    root = _py(tmp_path, 'db.save(Artifact(artifact_type="transcription"))\n')
    produced, dynamic = mod._producers(root)
    assert "transcription" in produced
    assert dynamic == []


def test_producer_module_constant_is_resolved(mod, tmp_path):
    """#4418's exact shape: the literal is behind a module-level constant.

    A check matching only inline literals would miss the very commit it exists
    for — PDF_TEXT_GEOMETRY_ARTIFACT = "text_geometry".
    """
    root = _py(tmp_path, 'PDF_GEO = "text_geometry"\ndb.save(Artifact(artifact_type=PDF_GEO))\n')
    produced, _ = mod._producers(root)
    assert "text_geometry" in produced


def test_dynamic_producer_is_reported_not_silently_dropped(mod, tmp_path):
    """Unresolvable sites must be COUNTED. A green run that quietly ignored
    them would convert "unknown" into "fine" — the #4425 failure mode.
    """
    root = _py(tmp_path, "db.save(Artifact(artifact_type=cfg.artifact_type))\n")
    produced, dynamic = mod._producers(root)
    assert produced == set()
    assert len(dynamic) == 1


def test_consumer_only_counted_inside_getArtifacts(mod, tmp_path):
    """A bare `type: "..."` regex over the Swift tree matches thousands of
    vendored KaTeX hits. Scoping to getArtifacts( is what keeps this usable.
    """
    root = _swift(
        tmp_path,
        'let x = ["type": "ordgroup"]\n'
        'let a = try await svc.getArtifacts(forDocumentId: id, type: "transcription")\n',
    )
    consumed = mod._consumers(root)
    assert set(consumed) == {"transcription"}


def test_the_check_fires_on_a_type_mismatch(mod, tmp_path):
    """THE test: producer writes one string, consumer asks for another."""
    py = _py(tmp_path, 'db.save(Artifact(artifact_type="text_geometry"))\n')
    sw = _swift(tmp_path, 'svc.getArtifacts(forDocumentId: id, type: "transcription")\n')
    produced, _ = mod._producers(py)
    consumed = mod._consumers(sw)
    unmatched = set(consumed) - produced
    assert unmatched == {"transcription"}, "a consumer asking for an unwritten type must be flagged"
    orphans = produced - set(consumed)
    assert orphans == {"text_geometry"}, "a producer nothing reads must be flagged"


def test_text_geometry_is_not_baselined(mod):
    """#4418 is still open: ingest writes "text_geometry", the overlay queries
    "transcription". Baselining it would silence a live defect — which is what
    an unexamined allowlist does (#2508).

    When #4418 is fixed, the overlay reads the type and this stays true because
    it is no longer an orphan at all. Only add it to the baseline if someone
    decides it is read generically.
    """
    assert "text_geometry" not in mod._ORPHAN_BASELINE


def test_docstring_states_the_dynamic_blind_spot(mod):
    doc = mod.__doc__ or ""
    assert "NOT" in doc and "dynamic" in doc.lower()


def test_enum_cases_are_extracted(mod, tmp_path):
    """The Swift `enum ArtifactType: String` is a THIRD declaration of the same
    contract, independent of both the server's writes and the client's queries.
    """
    root = _swift(
        tmp_path,
        "struct Artifact {\n"
        "    enum ArtifactType: String {\n"
        "        case transcription\n"
        "        case grouping\n"
        "    }\n"
        "}\n",
    )
    cases, path = _enum_path(mod, root)
    assert cases == {"transcription", "grouping"}
    assert path is not None


def _enum_path(mod, root):
    return mod._enum_cases(root)


def test_dead_enum_case_is_flagged(mod, tmp_path):
    """An enum case naming a type no server path writes is a claim the backend
    does not support. Live example on 2026-07-30: `embedding`, `grouping` and
    `segmentation` are declared and produced by nothing.
    """
    py = _py(tmp_path, 'db.save(Artifact(artifact_type="transcription"))\n')
    sw = _swift(
        tmp_path,
        "enum ArtifactType: String {\n    case transcription\n    case grouping\n}\n",
    )
    produced, _ = mod._producers(py)
    cases, _p = mod._enum_cases(sw)
    assert sorted(cases - produced) == ["grouping"]
