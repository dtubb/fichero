"""The native-row-container guard must fire on the shape it exists for.

`DocumentInspectorRelatedTab` shipped as a `VStack` of tappable rows while TWO
sibling files' doc comments already said "Native List(selection:), NOT a
hand-rolled VStack of tappable rows". The rule was written down twice and did
not bind, because a convention in a comment is not a mechanism.

So the thing that must be true of this guard is not that it passes today — it
passes today because the tree is clean, which is also what a dead detector
prints. Every fixture here is SYNTHESISED, so these test the reader rather
than the app, and the first one reproduces the `RelatedTab` shape exactly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("check_native_row_containers")


def _scan_source(tmp_path: Path, source: str, name: str = "Surface.swift"):
    (tmp_path / name).write_text(source, encoding="utf-8")
    offenders, files, foreach = guard.scan(tmp_path)
    return offenders, files, foreach


# ---------------------------------------------------------------------------
# It fires on the shape it exists for
# ---------------------------------------------------------------------------

RELATED_TAB_SHAPE = """
struct RelatedTabLike: View {
    var body: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(items, id: \\.id) { item in
                    RelatedRow(item: item)
                        .onTapGesture {
                            select(item)
                        }
                }
            }
        }
    }
}
"""


def test_it_fires_on_the_related_tab_shape(tmp_path):
    """The whole reason this file exists."""
    offenders, _files, _foreach = _scan_source(tmp_path, RELATED_TAB_SHAPE)

    assert len(offenders) == 1, "a tappable-row stack in a LazyVStack must be caught"
    assert offenders[0]["container"] == "LazyVStack"


def test_it_fires_on_a_bare_vstack_too(tmp_path):
    source = """
    struct S: View {
        var body: some View {
            VStack {
                ForEach(rows) { row in
                    Text(row.name).onTapGesture { pick(row) }
                }
            }
        }
    }
    """
    offenders, _f, _fe = _scan_source(tmp_path, source)

    assert len(offenders) == 1


def test_it_fires_on_a_simultaneous_tap_gesture(tmp_path):
    """`.simultaneousGesture(TapGesture())` is the same defect spelled
    differently — four spellings of double-click-to-open exist in the
    inspector alone, so matching only one would be a boundary error."""
    source = """
    struct S: View {
        var body: some View {
            LazyVStack {
                ForEach(rows) { row in
                    RowView(row)
                        .simultaneousGesture(TapGesture(count: 2).onEnded { open(row) })
                }
            }
        }
    }
    """
    offenders, _f, _fe = _scan_source(tmp_path, source)

    assert len(offenders) == 1


# ---------------------------------------------------------------------------
# ...and NOT on the things that are correct
# ---------------------------------------------------------------------------


def test_a_real_list_is_not_flagged(tmp_path):
    """The control. If this ever fails the guard has become noise, and a guard
    that cries wolf is disabled within a week — the same outcome as not
    writing it."""
    source = """
    struct S: View {
        var body: some View {
            List(items, selection: $selection) { item in
                RowView(item).onTapGesture { open(item) }
            }
        }
    }
    """
    offenders, _f, _fe = _scan_source(tmp_path, source)

    assert offenders == []


def test_a_foreach_nested_inside_a_list_section_is_not_flagged(tmp_path):
    """Ancestors are walked to the top, not just the immediate parent —
    `List { Section { ForEach } }` is idiomatic and correct."""
    source = """
    struct S: View {
        var body: some View {
            List(selection: $selection) {
                Section("Group") {
                    ForEach(rows) { row in
                        RowView(row).onTapGesture { open(row) }
                    }
                }
            }
        }
    }
    """
    offenders, _f, _fe = _scan_source(tmp_path, source)

    assert offenders == []


def test_a_grid_of_tiles_is_not_flagged(tmp_path):
    """A `List` cannot lay out a wrapping tile grid, so this rule does not
    apply. The first draft DID flag grids — three of them — and allowlisting
    those would have meant three entries whose reason was "the rule does not
    apply here", which is a boundary error wearing an allowlist's clothes.
    """
    source = """
    struct S: View {
        var body: some View {
            ScrollView {
                LazyVGrid(columns: columns) {
                    ForEach(docs) { doc in
                        Tile(doc).onTapGesture { select(doc) }
                    }
                }
            }
        }
    }
    """
    offenders, _f, _fe = _scan_source(tmp_path, source)

    assert offenders == [], "a grid is not a stack of rows"


def test_a_stack_of_rows_with_no_tap_handler_is_not_flagged(tmp_path):
    """Both halves of the conjunction are required. A read-only stack of
    labels is not a selection surface and turning it into a `List` would be
    adding an affordance for nothing."""
    source = """
    struct S: View {
        var body: some View {
            LazyVStack {
                ForEach(lines) { line in
                    Text(line.text)
                }
            }
        }
    }
    """
    offenders, _f, _fe = _scan_source(tmp_path, source)

    assert offenders == []


def test_a_commented_out_example_does_not_trip_it(tmp_path):
    """Comments are stripped before matching. This guard's own documentation
    quotes the forbidden shape, and a detector that reads its own docs as
    violations is the too-broad failure that condemned correct accessibility
    code this morning."""
    source = """
    struct S: View {
        var body: some View {
            // LazyVStack {
            //     ForEach(rows) { row in
            //         RowView(row).onTapGesture { open(row) }
            //     }
            // }
            List(rows, selection: $sel) { row in RowView(row) }
        }
    }
    """
    offenders, _f, _fe = _scan_source(tmp_path, source)

    assert offenders == []


# ---------------------------------------------------------------------------
# Blindness (EPIC #4487)
# ---------------------------------------------------------------------------


def test_it_reports_blind_when_the_population_is_too_small():
    """The floor sits on the SCAN POPULATION, not on violations found.

    This guard is expected to sit at zero forever, so "found nothing" is both
    its healthy state and its broken state. Only the population separates
    them.
    """
    with pytest.raises(SystemExit) as exit_info:
        guard._require_population(files_scanned=0, foreach_seen=0)

    assert exit_info.value.code == 2, "blindness is exit 2, never 0 or 1"


def test_a_missing_scan_root_is_also_blind(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["x", "--root", str(tmp_path / "gone")])

    assert guard.main() == 2


def test_the_floor_is_quiet_on_the_real_tree():
    """And it must NOT fire in normal operation. A guard that cries blind on a
    healthy tree gets disabled, which is the same outcome as never writing
    it."""
    offenders, files, foreach = guard.scan(guard.VIEWS_DIR)

    assert files >= guard.MIN_FILES, f"only {files} files — floor is too high or the tree moved"
    assert foreach >= guard.MIN_FOREACH, f"only {foreach} ForEach constructs found"
    assert offenders is not None


# ---------------------------------------------------------------------------
# The allowlist records reasons, not merely names
# ---------------------------------------------------------------------------


def test_every_allowlist_entry_carries_a_real_reason():
    """An exception without a reason is indistinguishable from debt someone
    silenced. `check_dead_files` learned this the same way."""
    entries = json.loads(guard.ALLOWLIST.read_text())

    assert entries, "an empty allowlist means the one known design got dropped"
    for key, reason in entries.items():
        assert len(reason) > 80, f"{key}: a one-line reason is not a reason"
        assert ".swift" in reason or ":" in reason, (
            f"{key}: the reason must point at where the rationale lives"
        )


def test_allowlisted_files_still_exist():
    """A stale entry silences a file that has moved — and the next tappable
    stack written at that path inherits the exemption."""
    for key in json.loads(guard.ALLOWLIST.read_text()):
        assert (guard.VIEWS_DIR / key).exists(), f"{key} is allowlisted but gone"
