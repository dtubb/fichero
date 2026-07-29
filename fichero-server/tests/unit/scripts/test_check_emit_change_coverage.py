from __future__ import annotations

import sys
import importlib.util
from pathlib import Path


_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_emit_change_coverage.py"
)
_SPEC = importlib.util.spec_from_file_location("check_emit_change_coverage", _SCRIPT)
assert _SPEC and _SPEC.loader
check_emit_change_coverage = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_emit_change_coverage  # register so @dataclass can resolve its module
_SPEC.loader.exec_module(check_emit_change_coverage)  # type: ignore[attr-defined]


def _write_route(path: Path, method: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
from fastapi import APIRouter

router = APIRouter()


@router.{method}(\"/notes\")
def post_note():
    {body}
""",
        encoding="utf-8",
    )


def _write_store(root: Path, domain: str, name: str = "TestStore") -> None:
    models_dir = root / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / f"{name}.swift").write_text(
        f"""
final class {name}: ObservableDomainStore {{
    nonisolated var changeDomain: String {{ "{domain}" }}
}}
""",
        encoding="utf-8",
    )


def _write_api_module(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
from fichero_server.models import Artifact
from fichero_server.api.change_stream import emit_change


def persist(db):
{body}
""",
        encoding="utf-8",
    )


def test_observed_domains_from_store_file(tmp_path):
    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note",
        "annotation"
    ]
}
""",
        encoding="utf-8",
    )

    assert check_emit_change_coverage._observed_domains(root=tmp_path) == {"note", "annotation"}


def test_mutating_route_with_emit_change_is_not_a_gap(tmp_path):
    routes_dir = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "notes.py"
    _write_route(route_file, "post", "emit_change()\n    return {'ok': True}")

    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note"
    ]
}
""",
        encoding="utf-8",
    )

    rows = check_emit_change_coverage.scan(root=tmp_path)
    assert len(rows) == 1
    assert rows[0].emit_change
    assert rows[0].gap is False


def test_mutating_route_without_emit_change_is_gap(tmp_path):
    routes_dir = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "notes.py"
    _write_route(route_file, "post", "return {'ok': True}")

    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note"
    ]
}
""",
        encoding="utf-8",
    )

    rows = check_emit_change_coverage.scan(root=tmp_path)
    assert len(rows) == 1
    assert rows[0].emit_change is False
    assert rows[0].gap is True


def test_non_route_observable_save_without_emit_change_is_gap(tmp_path):
    service_file = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "services" / "artifacts.py"
    _write_api_module(
        service_file,
        """    artifact = Artifact(document_id="doc-1", artifact_type="ocr", content="text")
    db.save(artifact)
""",
    )

    rows = check_emit_change_coverage.scan_non_route_saves(root=tmp_path)

    assert len(rows) == 1
    assert rows[0].model == "Artifact"
    assert rows[0].domain == "artifact"
    assert rows[0].gap is True


def test_non_route_observable_save_with_nearby_emit_change_passes(tmp_path):
    service_file = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "services" / "artifacts.py"
    _write_api_module(
        service_file,
        """    artifact = Artifact(document_id="doc-1", artifact_type="ocr", content="text")
    db.save(artifact)
    emit_change(library_path="/tmp/lib.fichero", domains=["artifact"], target_ids=[artifact.id])
""",
    )

    rows = check_emit_change_coverage.scan_non_route_saves(root=tmp_path)

    assert len(rows) == 1
    assert rows[0].emit_change is True
    assert rows[0].gap is False


def test_non_route_observable_save_with_allow_comment_passes(tmp_path):
    service_file = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "services" / "artifacts.py"
    _write_api_module(
        service_file,
        """    artifact = Artifact(document_id="doc-1", artifact_type="ocr", content="text")
    db.save(artifact)  # emit-change: allow imported by route owner
""",
    )

    rows = check_emit_change_coverage.scan_non_route_saves(root=tmp_path)

    assert len(rows) == 1
    assert rows[0].allowed is True
    assert rows[0].gap is False


def test_non_route_equivalent_save_of_direct_observable_model_is_gap(tmp_path):
    service_file = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "services" / "artifacts.py"
    _write_api_module(
        service_file,
        """    writer.save(Artifact(document_id="doc-1", artifact_type="ocr", content="text"))
""",
    )

    rows = check_emit_change_coverage.scan_non_route_saves(root=tmp_path)

    assert len(rows) == 1
    assert rows[0].model == "Artifact"
    assert rows[0].gap is True


def test_route_handlers_remain_covered_by_route_logic(tmp_path):
    routes_dir = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "artifacts.py"
    _write_route(
        route_file,
        "post",
        """artifact = Artifact(document_id="doc-1", artifact_type="ocr", content="text")
    db.save(artifact)
    return {'ok': True}""",
    )
    _write_store(tmp_path, "artifact", "ArtifactStore")

    route_rows = check_emit_change_coverage.scan(root=tmp_path)
    save_rows = check_emit_change_coverage.scan_non_route_saves(root=tmp_path)

    assert len(route_rows) == 1
    assert route_rows[0].domain == "artifact"
    assert route_rows[0].gap is True
    assert save_rows == []


def test_new_observable_domain_route_is_derived_from_model_mapping(tmp_path, monkeypatch):
    routes_dir = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "widgets.py"
    _write_route(route_file, "post", "emit_change()\n    return {'ok': True}")
    _write_store(tmp_path, "widget", "WidgetStore")
    monkeypatch.setitem(
        check_emit_change_coverage.OBSERVABLE_DOMAIN_MODELS,
        "widget",
        {"Widget"},
    )

    rows = check_emit_change_coverage.scan(root=tmp_path)

    assert len(rows) == 1
    assert rows[0].domain == "widget"
    assert rows[0].emit_change is True


def test_exempt_route_is_not_reported_as_gap(tmp_path, monkeypatch):
    routes_dir = tmp_path / "fichero-server" / "src" / "fichero" / "api" / "routes"
    route_file = routes_dir / "notes.py"
    _write_route(route_file, "post", "return {'ok': True}")

    models_dir = tmp_path / "fichero" / "fichero" / "Models"
    models_dir.mkdir(parents=True)
    (models_dir / "NoteStore.swift").write_text(
        """
class NoteStore {
    let changeDomains: Set<String> = [
        "note"
    ]
}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        check_emit_change_coverage,
        "EXEMPT",
        {"fichero-server/src/fichero_server/api/routes/notes.py::post_note"},
    )

    rows = check_emit_change_coverage.scan(root=tmp_path)
    assert len(rows) == 1
    assert rows[0].gap is True
    gaps = {
        row.key: row
        for row in rows
        if row.gap and row.key not in check_emit_change_coverage.EXEMPT
    }
    assert gaps == {}


# ---------------------------------------------------------------------------
# Terminal-node emit coverage (#2518): the contract that should have caught the
# missing completion + kg-finalize broadcasts. These nodes live outside
# api/routes, so the route/save scans never saw them.
# ---------------------------------------------------------------------------


def test_required_terminal_emits_present_on_real_tree():
    """The real tree must satisfy the terminal-node emit contract (the #2518
    fix is in place)."""
    assert check_emit_change_coverage.scan_required_terminal_emits() == []


def test_required_terminal_emits_flags_missing(tmp_path):
    """If a terminal node stops broadcasting, the guardrail FAILS (this is the
    regression it now prevents)."""
    rel = "fichero-server/src/fichero_server/workflows/completion.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def complete_run_documents(db, ids):\n"
        "    for i in ids:\n"
        "        db.save(i)\n",  # marks completed but never emits — the bug
        encoding="utf-8",
    )
    required = ((rel, frozenset({"emit_change"})),)
    violations = check_emit_change_coverage.scan_required_terminal_emits(
        root=tmp_path, required=required
    )
    assert len(violations) == 1
    assert "missing required emit" in violations[0]


def test_required_terminal_emits_passes_when_present(tmp_path):
    rel = "node.py"
    (tmp_path / rel).write_text(
        "def finalize():\n"
        "    emit_change('/lib/A.fichero', type='document.updated')\n",
        encoding="utf-8",
    )
    required = ((rel, frozenset({"emit_change"})),)
    assert (
        check_emit_change_coverage.scan_required_terminal_emits(
            root=tmp_path, required=required
        )
        == []
    )
