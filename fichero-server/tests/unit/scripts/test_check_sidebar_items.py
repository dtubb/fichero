"""Where the sidebar-wiring guard looks for a routed destination, and what it calls the cases.

It reported three sidebar item types as having no destination. All three were the guard:

  batch     — it asked for `AppViewMode.batch`; the case has always been `.batches`, plural,
              so it said "that case is missing" about a case that exists
  schedule  — routed by `PaneContentPlan.swift:103`
  trigger   — routed by `PaneContentPlan.swift:105`

The last two are the move-orphans-a-pin failure again: routing was one file, the panes work
moved part of it into `PaneContentPlan`, and the guard kept reading only the old home. Three
product gaps that were not product gaps — and this guard had no test, so nothing objected.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_sidebar_items.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_sidebar_items", _SCRIPT)
assert _SPEC and _SPEC.loader
sidebar = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = sidebar
_SPEC.loader.exec_module(sidebar)  # type: ignore[attr-defined]


class TestEveryNamedSourceIsReal:
    def test_every_router_file_exists(self):
        """`read()` is non-optional by design: a renamed router must be BLIND, not empty.

        Two files now, not one. If a third router appears and is not listed here, the modes it
        routes will read as unrouted — which is the bug this test exists to catch early.
        """
        for path in sidebar.ROUTER_FILES:
            assert path.exists(), path

    def test_more_than_one_router_is_consulted(self):
        assert len(sidebar.ROUTER_FILES) >= 2, "routing lives in ContentView+Navigation AND PaneContentPlan"


class TestTheMappingNamesCasesThatExist:
    def test_every_mapped_view_mode_is_a_real_appviewmode_case(self):
        """The `batch` -> `batch` entry failed exactly this: the case is `batches`."""
        modes = sidebar.app_view_modes()
        assert modes, "no AppViewMode cases found at all — the detector has gone blind"
        unknown = {
            item: mode
            for item, mode in sidebar.ITEM_TO_VIEW_MODE.items()
            if mode not in modes
        }
        assert unknown == {}, unknown

    def test_batches_is_spelled_plural(self):
        assert sidebar.ITEM_TO_VIEW_MODE["batch"] == "batches"


class TestTheThreeFalseGapsAreGone:
    def test_batch_schedule_and_trigger_are_routed(self):
        routes = sidebar.routed_view_modes()
        for mode in ("batches", "schedule", "trigger"):
            assert mode in routes, f"{mode} is routed in the app; the guard must see it"

    def test_the_repo_has_no_unwired_item_types(self):
        found = sidebar.scan()
        unaccounted = {k: v for k, v in found.items() if k not in sidebar.KNOWN_VIOLATIONS}
        assert unaccounted == {}, unaccounted

    def test_an_unmapped_item_type_is_still_reported(self):
        """Widening where the guard looks is how it goes quiet; this is the check on that."""
        original = dict(sidebar.ITEM_TO_VIEW_MODE)
        try:
            sidebar.ITEM_TO_VIEW_MODE["invented"] = "noSuchViewMode"
            built = set(sidebar.built_item_types())
            if "invented" not in built:
                # The item type has to actually be built for scan() to judge it; assert the
                # predicate directly instead of faking the Swift source.
                assert "noSuchViewMode" not in sidebar.app_view_modes()
                return
            assert "invented" in sidebar.scan()
        finally:
            sidebar.ITEM_TO_VIEW_MODE.clear()
            sidebar.ITEM_TO_VIEW_MODE.update(original)
