"""Tests for the #4331 view-type depth-bound guardrail.

Every fixture below SYNTHESISES its own violation in a tmp tree. Nothing is
borrowed from the committed source, so none of these rot when the real barriers
legitimately move — and, more importantly, none of them can pass by accident
because the real tree happens to be in the right shape today.

The crash being guarded is a main-thread stack overflow in
`swift_getTypeByMangledNode` on iOS (1MB stack vs macOS's 8MB), so the failure
mode this suite really cares about is the SILENT one: a sweep deletes an
`AnyView` that looks redundant, everything stays green, and the app dies at
launch on a physical iPhone.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "check_view_type_depth_bounds.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("check_view_type_depth_bounds")


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _run(app_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--app-dir", str(app_dir)],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Fixtures — the two proven shapes, rewritten from scratch
# ---------------------------------------------------------------------------

_INTACT_BARRIER = """
extension ContentView {
    @ViewBuilder
    var someCase: some View {
        // AnyView is load-bearing (#4331): the composed case generic nested in
        // the shell's getter chain overflowed the iOS 1MB main stack.
        AnyView(DeeplyComposedThing(a: 1, b: 2))
    }
}
"""

_BROKEN_BARRIER = """
extension ContentView {
    @ViewBuilder
    var someCase: some View {
        // AnyView is load-bearing (#4331): the composed case generic nested in
        // the shell's getter chain overflowed the iOS 1MB main stack.
        DeeplyComposedThing(a: 1, b: 2)
    }
}
"""

_SECOND_INTACT_BARRIER = """
extension ContentView {
    @ViewBuilder
    var compactStack: some View {
        NavigationStack {
            // AnyView is load-bearing (#4331): the iPhone-only stack sits at the
            // deepest point of the shell's getter chain.
            AnyView(contentWithOptionalModeRail)
        }
    }
}
"""


def _two_intact(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    _write(app, "Nav.swift", _INTACT_BARRIER)
    _write(app, "Compact.swift", _SECOND_INTACT_BARRIER)
    return app


# ---------------------------------------------------------------------------
# It fires when the erasure is deleted but the comment survives
# ---------------------------------------------------------------------------


def test_declared_barrier_without_its_erasure_is_a_violation(tmp_path):
    app = tmp_path / "app"
    _write(app, "Nav.swift", _BROKEN_BARRIER)
    _write(app, "Compact.swift", _SECOND_INTACT_BARRIER)

    intact, broken = guard.scan(app)

    assert len(broken) == 1, "the stripped AnyView must be reported"
    assert broken[0]["file"].endswith("Nav.swift")
    assert len(intact) == 1


def test_stripped_erasure_fails_the_script_with_exit_1(tmp_path):
    app = tmp_path / "app"
    _write(app, "Nav.swift", _BROKEN_BARRIER)
    _write(app, "Compact.swift", _SECOND_INTACT_BARRIER)

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "lost the AnyView erasure" in result.stdout


# ---------------------------------------------------------------------------
# It passes on the healthy shape (so a red run means something)
# ---------------------------------------------------------------------------


def test_intact_barriers_pass(tmp_path):
    result = _run(_two_intact(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_multiline_comment_between_marker_and_erasure_still_passes(tmp_path):
    """The real sites carry 4-5 lines of explanation before the AnyView."""
    app = tmp_path / "app"
    _write(app, "Compact.swift", _SECOND_INTACT_BARRIER)
    _write(
        app,
        "Nav.swift",
        """
extension ContentView {
    var someCase: some View {
        // AnyView is load-bearing (#4331): the fully composed library-case
        // generic, nested inside the shell's getter chain, produced a mangled
        // type whose runtime metadata instantiation recursed past the 1MB
        // iOS main-thread stack (fine on macOS's 8MB) — instant launch crash.
        // Erasing at the case boundary bounds the type depth on every layout.
        AnyView(LibraryView(documents: docs))
    }
}
""",
    )

    result = _run(app)

    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Near misses it must NOT fire on — a guard that cries wolf gets disabled
# ---------------------------------------------------------------------------


def test_unrelated_load_bearing_comments_are_not_barriers(tmp_path):
    """~19 files say "load-bearing" about isolation, defaults and Equatable.

    None of them owe this guard an AnyView. Only the exact
    "AnyView is load-bearing" phrasing declares a depth bound.
    """
    app = _two_intact(tmp_path)
    _write(
        app,
        "Other.swift",
        """
/// `nonisolated` is load-bearing: this is read from a cooperative-pool suite.
/// `= nil` is load-bearing: three call sites omit this arg.
nonisolated static let pattern = "x"
""",
    )

    result = _run(app)

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_distant_anyview_cannot_satisfy_an_unrelated_marker(tmp_path):
    """An `AnyView(` 40 lines later is a different expression entirely.

    Without a window the guard would pass on any file that mentions AnyView
    anywhere — the exact "measured nothing, reported success" failure.
    """
    app = tmp_path / "app"
    _write(app, "Compact.swift", _SECOND_INTACT_BARRIER)
    filler = "\n".join(f"    // filler {n}" for n in range(40))
    _write(
        app,
        "Nav.swift",
        f"""
extension ContentView {{
    var someCase: some View {{
        // AnyView is load-bearing (#4331): bounds the composed type depth.
        DeeplyComposedThing(a: 1, b: 2)
{filler}
        AnyView(SomethingCompletelyElse())
    }}
}}
""",
    )

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Blindness — the whole point. Absence must never read as safety.
# ---------------------------------------------------------------------------


def test_deleting_both_erasure_and_comment_still_fails(tmp_path):
    """The escape hatch a naive marker-based guard leaves wide open.

    A sweep that removes the AnyView *and* the comment explaining it leaves
    nothing to check. Counting barriers against a floor is what closes that,
    so "I found no barriers" cannot mean "there are no violations".
    """
    app = tmp_path / "app"
    _write(
        app,
        "Nav.swift",
        """
extension ContentView {
    var someCase: some View { DeeplyComposedThing(a: 1, b: 2) }
}
""",
    )

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "proven necessary by a device crash" in result.stdout


def test_an_entirely_empty_tree_does_not_pass(tmp_path):
    """The #4382 shape: a guard run against nothing reported success.

    An empty (but existing) app dir has zero barriers, which is below the
    floor, so it fails rather than passing vacuously.
    """
    app = tmp_path / "app"
    app.mkdir()

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr


def test_missing_scan_root_is_blind_not_a_pass(tmp_path):
    """A moved or renamed tree must exit 2, distinctly from exit 1.

    Exit 1 means "I looked and found violations". Exit 2 means "I could not
    look". Collapsing them is how a guardrail stops existing without anyone
    noticing.
    """
    result = _run(tmp_path / "does-not-exist")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLIND" in result.stderr


def test_the_real_tree_still_carries_its_proven_barriers():
    """One live, unstubbed check against the committed source.

    Everything above runs on synthetic fixtures, which means all of it would
    stay green if the real erasures were deleted tomorrow. This is the assertion
    that actually protects the shipped app.
    """
    intact, broken = guard.scan(guard.APP_DIR)

    assert not broken, f"a declared #4331 barrier lost its erasure: {broken}"
    assert len(intact) >= guard.MIN_BARRIERS, (
        "the two AnyView erasures proven necessary by the v2026.07.29 iPhone "
        f"crash are down to {len(intact)}"
    )
