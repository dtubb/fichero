"""Unit tests for scripts/check_store_wholesale_reload.py (pins the
observable-data-layer / no-wholesale-list-rerender rule, #4824).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_store_wholesale_reload.py"
_SPEC = importlib.util.spec_from_file_location("check_store_wholesale_reload", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


STORE_WITH_RELOAD_ON_DELETE = """
import Observation

@Observable
final class ThingStore {
    private(set) var items: [Thing] = []

    func delete(_ thing: Thing) async {
        await service.delete(thing.id)
        await reload()
    }

    func reload() async {
        items = try await service.getThings()
    }
}
"""

STORE_WITH_WHOLESALE_REASSIGN_ON_UPDATE = """
@Observable
final class ThingStore {
    private(set) var items: [Thing] = []

    func update(_ thing: Thing) async {
        let updated = try await service.update(thing)
        items = service.items
    }
}
"""

STORE_WITH_CORRECT_SPLICE = """
@Observable
final class ThingStore {
    private(set) var items: [Thing] = []

    func update(_ thing: Thing) async {
        let updated = try await service.update(thing)
        if let index = items.firstIndex(where: { $0.id == updated.id }) {
            items[index] = updated
        }
    }

    func append(_ thing: Thing) {
        items.append(thing)
    }

    func remove(_ id: String) {
        items.removeAll { $0.id == id }
    }
}
"""

STORE_WITH_MULTILINE_SIGNATURE = """
@Observable
final class ThingStore {
    private(set) var items: [Thing] = []

    func addThing(
        name: String,
        tags: [String] = []
    ) async -> Thing? {
        let result = await service.add(name: name, tags: tags)
        if result != nil { items = service.items }
        return result
    }
}
"""

NOT_A_STORE_CLASS = """
@Observable
final class ThingHelper {
    private(set) var items: [Thing] = []

    func delete(_ thing: Thing) async {
        await reload()
    }

    func reload() async {}
}
"""


def _write(tmp_path: Path, source: str, name: str = "ThingStore.swift") -> Path:
    root = tmp_path / "fichero" / "fichero" / "Models"
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(source, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "ROOT", tmp_path / "fichero" / "fichero")
    monkeypatch.setattr(_mod, "ALLOWLIST_PATH", tmp_path / "allowlist.json")
    return tmp_path


def test_fires_on_reload_call_inside_delete(tmp_path):
    _write(tmp_path, STORE_WITH_RELOAD_ON_DELETE)
    _, findings = _mod.scan_tree()
    assert any(f["method"] == "delete" for f in findings)


def test_fires_on_whole_array_reassignment_in_update(tmp_path):
    _write(tmp_path, STORE_WITH_WHOLESALE_REASSIGN_ON_UPDATE)
    _, findings = _mod.scan_tree()
    assert any(f["method"] == "update" for f in findings)


def test_does_not_fire_on_index_splice_append_or_remove_all(tmp_path):
    _write(tmp_path, STORE_WITH_CORRECT_SPLICE)
    _, findings = _mod.scan_tree()
    assert findings == []


def test_does_not_fire_inside_load_or_reload_itself(tmp_path):
    _write(tmp_path, STORE_WITH_RELOAD_ON_DELETE)
    _, findings = _mod.scan_tree()
    assert not any(f["method"] == "reload" for f in findings)


def test_handles_multiline_function_signature(tmp_path):
    """A `func` whose parameter list spans several lines before the opening
    `{` must still have its BODY scanned — the brace-depth walk has to find
    the real opening brace, not assume it's on the `func` line."""
    _write(tmp_path, STORE_WITH_MULTILINE_SIGNATURE)
    _, findings = _mod.scan_tree()
    assert any(f["method"] == "addThing" for f in findings)


def test_does_not_fire_on_a_non_store_class(tmp_path):
    _write(tmp_path, NOT_A_STORE_CLASS, name="ThingHelper.swift")
    _, findings = _mod.scan_tree()
    assert findings == []


def test_zero_stores_found_fails(tmp_path, capsys):
    # No files written — an empty Models/ dir.
    (tmp_path / "fichero" / "fichero" / "Models").mkdir(parents=True)
    rc = _mod.check()
    out = capsys.readouterr().out + capsys.readouterr().err
    assert rc == 2


def test_allowlisted_finding_passes(tmp_path):
    _write(tmp_path, STORE_WITH_RELOAD_ON_DELETE)
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": str(tmp_path / "fichero" / "fichero" / "Models" / "ThingStore.swift"),
         "method": "delete", "reason": "known, tracked", "issue": 9999},
    ]), encoding="utf-8")
    assert _mod.check() == 0


def test_stale_allowlist_entry_fails(tmp_path):
    _write(tmp_path, STORE_WITH_CORRECT_SPLICE)  # no findings at all
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": "fichero/fichero/Models/Gone.swift", "method": "delete",
         "reason": "no longer exists", "issue": 1},
    ]), encoding="utf-8")
    assert _mod.check() == 1


def test_allowlist_entry_without_reason_fails(tmp_path):
    _write(tmp_path, STORE_WITH_RELOAD_ON_DELETE)
    _mod.ALLOWLIST_PATH.write_text(json.dumps([
        {"file": str(tmp_path / "fichero" / "fichero" / "Models" / "ThingStore.swift"),
         "method": "delete", "reason": "", "issue": 9999},
    ]), encoding="utf-8")
    assert _mod.check() == 1
