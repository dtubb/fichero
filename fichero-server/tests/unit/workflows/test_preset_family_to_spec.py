"""`workflows.defaults.duplication-regrown` (#4738): the shipped preset set must not regrow near-duplicates unnoticed.

WHY: reviews found topologically identical transcription presets and Catalogue in three shapes. Pruning needs a product
ruling; this guard stops the set growing further: no two presets may be identical, and a new group of presets that share one
topology is a deliberate addition to KNOWN_SHARED_TOPOLOGY, not an accident.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

PRESETS = Path(__file__).resolve().parents[3] / "src/fichero_server/resources/default_workflows"

#: Topology (the sorted tools) -> how many presets share it today. Raising a number needs a reason in the commit.
KNOWN_SHARED_TOPOLOGY = {
    ("convert", "files"): 3,
    ("detect_regions", "files"): 4,
    ("consistency-check", "files", "table_extract"): 2,  # Extract Table and Accounts to CSV: both end in the consistency check (Step 3.3)
    ("analyze", "files"): 3,
    ("files", "transcribe"): 11,
}


def _presets() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(PRESETS.glob("*.json"))]


def test_no_two_presets_are_the_same_graph_with_the_same_settings():
    seen: dict[str, str] = {}
    for d in _presets():
        key = json.dumps([(n["tool"], n.get("config", {})) for n in sorted(d["nodes"], key=lambda n: n["tool"])], sort_keys=True)
        assert key not in seen, f"{d['name']!r} repeats {seen[key]!r}: same tools, same settings"
        seen[key] = d["name"]


def test_presets_that_share_a_topology_are_the_known_groups_and_no_bigger():
    groups = collections.Counter(tuple(sorted(n["tool"] for n in d["nodes"])) for d in _presets())
    shared = {k: v for k, v in groups.items() if v > 1}
    for topology, count in shared.items():
        assert topology in KNOWN_SHARED_TOPOLOGY, f"a new group of {count} presets shares {topology}: add it on purpose"
        assert count <= KNOWN_SHARED_TOPOLOGY[topology], f"{topology} grew to {count}"
