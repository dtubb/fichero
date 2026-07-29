"""#2710 — transcribe-family preset convention contract.

Locks the i16 config-consistency convention + the per-page fan-out invariant
across the shipped transcribe presets so they can't silently drift apart again
(the "I have to fiddle every time" driver). Scoped to the safe, mechanical
half: this does NOT enforce the i15 display-name rename / preset-count
reduction (retire+merge of shipped, auto-upgrading graphs), which is a
destructive taxonomy change gated on Daniel — see the issue.

Two invariants, asserted over resources/default_workflows/*.json:
  1. Every `transcribe`-tool node sets `vision_mode` AND `language` in config
     (so Apple Vision is reachable and language isn't hard-pinned).
  2. Per-page fan-out: every `transcribe` node in a runnable preset (one that
     has a source node) is reachable from a SOURCE_TOOLS node — directly or via
     a route_map'd classify branch — so the builder fans it out per page rather
     than processing a whole document at once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_PRESETS_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "fichero_server"
    / "resources"
    / "default_workflows"
)


def _transcribe_presets() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if any(n.get("tool") == "transcribe" for n in data.get("nodes", [])):
            out.append((path.name, data))
    return out


_PRESETS = _transcribe_presets()


def test_presets_dir_has_transcribe_family():
    # Guards against a glob/path regression silently passing the suite.
    assert _PRESETS, f"no transcribe presets found under {_PRESETS_DIR}"


@pytest.mark.parametrize("name,preset", _PRESETS, ids=[p[0] for p in _PRESETS])
def test_transcribe_nodes_set_vision_mode_and_language(name, preset):
    for node in preset["nodes"]:
        if node.get("tool") != "transcribe":
            continue
        cfg = node.get("config") or {}
        missing = [k for k in ("vision_mode", "language") if k not in cfg]
        assert not missing, (
            f"{name}: transcribe node {node.get('id')!r} missing {missing} — "
            "i16 convention requires explicit vision_mode + language"
        )


def _reachable_from_sources(preset: dict) -> tuple[set[str], set[str]]:
    """Return (source_node_ids, reachable_node_ids) following edges + route_map."""
    from fichero_server.workflows.builder import SOURCE_TOOLS

    nodes = {n["id"]: n for n in preset["nodes"]}
    adj: dict[str, set[str]] = {}
    for e in preset.get("edges", []):
        src = e.get("source")
        if e.get("route_map"):
            for tgt in e["route_map"].values():
                adj.setdefault(src, set()).add(tgt)
        elif e.get("target"):
            adj.setdefault(src, set()).add(e["target"])

    sources = {nid for nid, n in nodes.items() if n.get("tool") in SOURCE_TOOLS}
    seen = set(sources)
    stack = list(sources)
    while stack:
        cur = stack.pop()
        for nxt in adj.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return sources, seen


def _is_component(preset: dict) -> bool:
    """A sub-workflow component declares config.input_contract — its files come
    from the invoking parent, so per-page fan-out is the caller's contract."""
    return bool((preset.get("config") or {}).get("input_contract"))


@pytest.mark.parametrize("name,preset", _PRESETS, ids=[p[0] for p in _PRESETS])
def test_transcribe_nodes_qualify_for_per_page_fanout(name, preset):
    if _is_component(preset):
        pytest.skip(f"{name}: sub-workflow component (input_contract — parent-driven)")

    sources, reachable = _reachable_from_sources(preset)
    assert sources, (
        f"{name}: runnable transcribe preset has no source node "
        "(files/collection/folder/search) to drive per-page fan-out"
    )

    transcribe_ids = [
        n["id"] for n in preset["nodes"] if n.get("tool") == "transcribe"
    ]
    unreached = [t for t in transcribe_ids if t not in reachable]
    assert not unreached, (
        f"{name}: transcribe nodes {unreached} are not reachable from a source "
        "tool (files/collection/folder/search) — they would NOT fan out per "
        "page. Wire them from the source (directly or via classify route_map)."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
