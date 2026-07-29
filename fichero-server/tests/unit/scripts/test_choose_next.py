from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "scripts" / "choose_next.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("choose_next_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_roadmap_uses_priority_spine_not_narrative_tiers() -> None:
    choose_next = _load_module()

    text = """
# Fichero — Roadmap

### ▶▶ REFINED ORDER (2026-06-11 PM design session)
- Milestone: **Developer Experience** (#64)

# ▶▶ PRIORITY SPINE — machine-read by `scripts/choose_next.py`

## Tier 1 — Dev & Build Harness
- Milestone: **Dev & Build Harness**  (due 2026-07-05)

## Tier 10 — Infra & hardening
- Milestone: **Developer Experience**  (due 2026-12-02)
"""

    tiers = choose_next.parse_roadmap_from_text_for_test(text)

    assert [tier.key for tier in tiers] == ["1", "10"]
    assert tiers[0].milestones == ("Dev & Build Harness",)
    assert tiers[1].milestones == ("Developer Experience",)


def test_select_batch_prefers_dev_build_harness_before_developer_experience() -> None:
    choose_next = _load_module()

    tiers = choose_next.parse_roadmap_from_text_for_test(
        """
# ▶▶ PRIORITY SPINE — machine-read by `scripts/choose_next.py`

## Tier 1 — Dev & Build Harness
- Milestone: **Dev & Build Harness**

## Tier 10 — Infra & hardening
- Milestone: **Developer Experience**
"""
    )

    issues = [
        choose_next.Issue(2871, "verify_all planner", ("backend",), (), "Dev & Build Harness"),
        choose_next.Issue(2888, "CLI keystone", ("backend",), (), "Developer Experience"),
    ]

    selection = choose_next.select_batch(tiers, issues)

    assert selection["milestone"] == "Dev & Build Harness"
    assert [issue["number"] for issue in selection["issues"]] == [2871]
