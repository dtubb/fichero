"""'Transcribe (Auto-Detect)' carries COPIES of four presets' prompts.

The preset classifies a page's script type and routes to one of four branches.
Each branch is the same tool and the same config as a standalone preset —
Transcribe Typescript, Transcribe Manuscript, Transcribe HTR, Transcribe
Paleography — and each carries that preset's ~40-line prompt inline, verbatim.
Measured 2026-09-04: all four are byte-identical to their source.

That means every prompt tune has to be applied in two places. Two tunes landed
in one night (49bdad4eb, 6a1ca277a) and both had to be repeated. The fifth
embedded prompt in this preset — the paleography review pass — has ALREADY
drifted from its source (Paleographer Review's first pass) and is deliberately
different: it folds three review passes into one. So it is not pinned here.
Divergence is allowed; it just must not happen by accident.

The right fix is structural — either a prompt-reference mechanism in the preset
format, or making Auto-Detect a router over the four real presets via
sub_workflow nodes (the pattern catalogue.json v6 already uses). Both change
more than a prompt string and need live verification. Until one lands, this
test is the honest fallback: the copies stay identical, or the gate says so.

When a source prompt legitimately changes: update BOTH files, bump the
auto-detect preset's preset_version, and refresh the preset manifest.

Nothing here touches a database or calls a model.
"""

from __future__ import annotations

import json

from fichero_server.workflows.default_workflows import _PRESETS_DIR as PRESETS_DIR

AUTO_DETECT = "transcribe_auto_detect.json"

# auto-detect branch node id -> (source preset file, source node id)
BRANCH_SOURCES = {
    "transcribe-ts": ("transcribe_typescript.json", "transcribe"),
    "transcribe-ms": ("transcribe_manuscript.json", "transcribe"),
    "transcribe-htr": ("transcribe_htr.json", "transcribe"),
    "transcribe-paleo": ("transcribe_paleography.json", "transcribe"),
}


def _prompt(preset_file: str, node_id: str) -> str:
    preset = json.loads((PRESETS_DIR / preset_file).read_text(encoding="utf-8"))
    for node in preset.get("nodes", []):
        if node.get("id") == node_id:
            prompt = (node.get("config") or {}).get("prompt")
            assert prompt, f"{preset_file}#{node_id} has no prompt"
            return prompt
    raise AssertionError(f"{preset_file} has no node '{node_id}'")


def _drifted(pairs: dict[str, tuple[str, str]]) -> list[str]:
    """Branch ids whose copied prompt no longer equals its source."""
    return sorted(label for label, (copy, source) in pairs.items() if copy != source)


def test_every_pinned_branch_exists() -> None:
    """Catch a rewiring that renames a branch node out from under this guard."""
    auto = json.loads((PRESETS_DIR / AUTO_DETECT).read_text(encoding="utf-8"))
    node_ids = {node.get("id") for node in auto.get("nodes", [])}
    missing = sorted(set(BRANCH_SOURCES) - node_ids)
    assert not missing, (
        f"{AUTO_DETECT} no longer has branch node(s): {missing}. If the preset "
        "was restructured (e.g. into sub_workflow nodes over the real presets), "
        "that is the intended fix — delete this test with the restructure."
    )


def test_auto_detect_branch_prompts_match_their_source_presets() -> None:
    drifted = _drifted(
        {
            f"{AUTO_DETECT}#{branch_id} != {source_file}#{source_node}": (
                _prompt(AUTO_DETECT, branch_id),
                _prompt(source_file, source_node),
            )
            for branch_id, (source_file, source_node) in BRANCH_SOURCES.items()
        }
    )

    assert not drifted, (
        "Auto-Detect's embedded prompt(s) have drifted from the preset they "
        "copy:\n  " + "\n  ".join(drifted) + "\n\nA user who picks Auto-Detect "
        "and a user who picks the named preset would get different "
        "transcriptions of the same page, with nothing in the UI saying so. "
        "Apply the change to both files, bump transcribe_auto_detect.json's "
        "preset_version, and refresh the preset manifest."
    )


# --- proof the guard fires -------------------------------------------------


def test_guard_catches_a_prompt_tune_applied_to_only_one_copy() -> None:
    tuned = "Transcribe the text.\nOutput plain text, no markdown."
    stale = "Transcribe the text."
    assert _drifted({"branch": (stale, tuned)}) == ["branch"]
    assert _drifted({"branch": (tuned, tuned)}) == []
