"""scripts/check_spec_app_evidence.py (dev-workflows.quality.spec-app-evidence, #7067).

An app behaviour is done only when its screen exists: an [OK]/[BUILT] behaviour whose scope names the app must cite a Swift
test, and a spec file with app behaviours must have a "What the person sees" / UX section that names the opener, the empty,
loading and error states and an acceptance line. Existing offenders sit in a baseline that may only shrink.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_app_evidence.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_spec_app_evidence", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)

UX_OK = """## What the person sees

Opened from the Window menu, "Models & Cluster" (Cmd-Shift-M). It shows one row per model with Install and Remove buttons.
Empty: "No models yet" with an Install button. Loading: a spinner row. Error: a red banner with Retry.
Acceptance: opening the window with no models shows the empty state (`fichero/Tests/UI/general/Models/ModelsWindowUITests.swift`).
"""


def _root(tmp_path: Path, files: dict[str, str]) -> Path:
    specs = tmp_path / "docs" / "contributor_manual" / "specs"
    for name, text in files.items():
        (specs / name).parent.mkdir(parents=True, exist_ok=True)
        (specs / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_an_ok_app_behaviour_citing_only_pytest_is_engine_done_the_app_part_is_not(tmp_path):
    root = _root(tmp_path, {"a.md": "- `m.one` — **[OK]** the app shows the model list. *Test:* `fichero-server/tests/unit/test_models.py`\n"})
    assert guard.engine_only_offenders(root) == {"docs/contributor_manual/specs/a.md::m.one"}


def test_a_swift_test_path_or_a_ui_test_satisfies_it_and_a_non_app_or_gap_line_is_not_judged(tmp_path):
    root = _root(tmp_path, {"a.md": (
        "- `m.one` — **[OK]** the app shows the list. *Test:* `fichero/Tests/Unit/general/Models/ModelListTests.swift`\n"
        "- `m.two` — **[BUILT]** the app opens it. *Test:* `fichero/Tests/UI/general/Models/ModelsWindowUITests.swift`\n"
        "- `m.three` — **[OK]** the engine lists models. *Test:* `fichero-server/tests/unit/test_models.py`\n"
        "- `m.four` — **[GAP]** (#1) the app shows it.\n"
        "- `m.five` — **[OK]** the engine writes it; the application layer is not involved. *Test:* `x.py`\n"
    )})
    assert guard.engine_only_offenders(root) == set()


def test_the_scope_text_runs_over_continuation_lines_after_the_tag(tmp_path):
    root = _root(tmp_path, {"a.md": "- `m.one` — **[OK]** (#5)\n  the sidebar in the app lists it.\n  *Test:* `t.py`\n"})
    assert guard.engine_only_offenders(root) == {"docs/contributor_manual/specs/a.md::m.one"}


def test_a_spec_with_app_behaviours_needs_a_ux_section_naming_opener_states_and_acceptance(tmp_path):
    body = "- `m.one` — **[GAP]** (#1) the app shows the list.\n\n"
    root = _root(tmp_path, {
        "none.md": body,
        "good.md": body + UX_OK,
        "thin.md": body + "## What the person sees\n\nA list.\n",
        "engine.md": "- `m.two` — **[OK]** the engine lists it. *Test:* `t.py`\n",
    })
    assert guard.no_ux_specs(root) == {"docs/contributor_manual/specs/none.md", "docs/contributor_manual/specs/thin.md"}
    assert guard.ux_problems(UX_OK) == []
    assert {"opener", "empty", "loading", "error", "acceptance"} <= set(guard.ux_problems("## UX\n\nA list.\n"))


def _write_baseline(root: Path, engine_only: list[str], no_ux: list[str]) -> Path:
    path = root / "baseline.json"
    path.write_text(json.dumps({"engine_only": engine_only, "no_ux_section": no_ux}), encoding="utf-8")
    return path


def test_a_new_offender_fails_a_baselined_one_passes_and_a_listed_line_that_now_passes_fails(tmp_path):
    root = _root(tmp_path, {"a.md": "- `m.one` — **[OK]** the app shows it. *Test:* `t.py`\n"})
    key = "docs/contributor_manual/specs/a.md::m.one"
    ux = "docs/contributor_manual/specs/a.md"
    new, stale = guard.judge(root, _write_baseline(root, [], [ux]))
    assert new == [f"engine_only: {key}"] and stale == []
    new, stale = guard.judge(root, _write_baseline(root, [key], [ux]))
    assert new == [] and stale == []
    (root / "docs/contributor_manual/specs/a.md").write_text(
        "- `m.one` — **[OK]** the app shows it. *Test:* `fichero/Tests/Unit/general/Models/ATests.swift`\n" + UX_OK, encoding="utf-8")
    new, stale = guard.judge(root, _write_baseline(root, [key], [ux]))
    assert new == [] and stale == [f"engine_only: {key}", f"no_ux_section: {ux}"]


def test_the_repo_baseline_matches_the_specs_today():
    new, stale = guard.judge(guard.REPO_ROOT, guard.BASELINE)
    assert new == [] and stale == []
