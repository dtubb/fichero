"""The #4479 blindness in `check_accessibility` cannot return.

Two detector bugs let this scanner report a labelled button as unlabelled, and
BOTH were silenced by `KNOWN_VIOLATIONS` rather than found:

1. the modifier chain stopped at the first continuation line not starting with
   ".", so a multi-line `.help(...)` hid every modifier below it — including
   `.accessibilityLabel`;
2. `Label(title, systemImage:)` was only recognised when `title` was a string
   LITERAL, so a menu row with a variable title read as icon-only.

Six allowlist entries turned out to document the tool's blind spots rather than
real gaps. An allowlist over a broken scanner is worse than no scanner: it
converts a defect into a reviewed, approved, permanent exception that nobody
revisits.

So these tests are about what the scanner can SEE. Every fixture is synthesised
here — none is lifted from the tree — so they keep testing the reader when the
app changes, and a fixture that would have passed before the fix is marked as
such.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("check_accessibility")


def _chain(source: str) -> str:
    """Collect the button chain starting at the first `Button` line."""
    lines = guard.code_lines(source)
    start = next(i for i, line in enumerate(lines) if "Button" in line)
    _end, snippet = guard._collect_button_chain(lines, start)
    return snippet


# ---------------------------------------------------------------------------
# Bug 1 — the chain must survive a multi-line modifier
# ---------------------------------------------------------------------------

MULTILINE_HELP = """
        Button {
            toggle()
        } label: {
            Image(systemName: "pencil")
        }
        .buttonStyle(.plain)
        .help(isDisabled
            ? "Not available for this document"
            : (isEditing
                ? "Done — return to viewing"
                : "Edit image"))
        .accessibilityLabel(isEditing ? "Done editing" : "Edit image")
"""


def test_a_multi_line_modifier_does_not_truncate_the_chain():
    """The exact shape that produced the false positive.

    Before the fix the walk stopped at `? "Not available..."`, so the
    `.accessibilityLabel` three lines lower was invisible and the button was
    reported MISSING.
    """
    chain = _chain(MULTILINE_HELP)

    assert ".accessibilityLabel(" in chain, (
        "the label below a multi-line .help must be seen"
    )


def test_that_button_is_not_reported_as_unlabelled():
    assert not guard._is_icon_only_button(_chain(MULTILINE_HELP))


def test_nested_brackets_inside_a_modifier_do_not_end_the_chain():
    """A modifier whose arguments contain their own parens and brackets."""
    source = """
        Button { act() } label: {
            Image(systemName: "square")
        }
        .contextMenu {
            Button("A") { a(["x", "y"]) }
        }
        .help(build(
            values: [1, 2, 3],
            other: (nested, tuple)
        ))
        .accessibilityLabel("Square")
"""
    assert ".accessibilityLabel(" in _chain(source)


# ---------------------------------------------------------------------------
# Bug 2 — a Label with a variable title is announced
# ---------------------------------------------------------------------------


def test_a_label_with_a_variable_title_is_not_icon_only():
    """`Label(label, systemImage: icon)` — a menu row whose title is passed in.

    VoiceOver announces it. The scanner used to require a string literal and
    reported five of these as unlabelled.
    """
    source = """
        Button(action: action) {
            Label(label, systemImage: icon)
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.control, .command]
        )
"""
    assert not guard._is_icon_only_button(_chain(source))


def test_a_label_with_a_literal_title_is_still_not_icon_only():
    source = """
        Button {
            act()
        } label: {
            Label("Rename", systemImage: "pencil")
        }
"""
    assert not guard._is_icon_only_button(_chain(source))


def test_an_icon_only_label_style_is_still_flagged():
    """`.labelStyle(.iconOnly)` strips the spoken title — the exclusion must
    survive the widened Label match, or bug 2's fix would hide real gaps."""
    source = """
        Button {
            act()
        } label: {
            Label("Rename", systemImage: "pencil")
        }
        .labelStyle(.iconOnly)
"""
    assert guard._is_icon_only_button(_chain(source))


# ---------------------------------------------------------------------------
# It must still catch the thing it exists for
# ---------------------------------------------------------------------------


def test_a_genuinely_unlabelled_icon_button_is_still_flagged():
    """The whole point. A scanner loosened twice has to be shown to still bite.

    If this ever passes, the two fixes above have been widened into blindness
    of their own — which is how a guard stops existing without anyone noticing.
    """
    source = """
        Button {
            act()
        } label: {
            Image(systemName: "star")
        }
        .buttonStyle(.plain)
        .help("Favourite")
"""
    assert guard._is_icon_only_button(_chain(source))


def test_an_unlabelled_button_with_a_multi_line_modifier_is_still_flagged():
    """Bug 1's fix must not make unlabelled buttons invisible instead.

    Seeing more of the chain is only an improvement if what it sees is judged;
    a walk that ran past the end and found nothing would look identical to a
    walk that found a label.
    """
    source = """
        Button {
            act()
        } label: {
            Image(systemName: "star")
        }
        .help(isOn
            ? "On"
            : "Off")
"""
    assert guard._is_icon_only_button(_chain(source))


def test_an_explicitly_hidden_control_is_not_flagged():
    """`.accessibilityHidden(true)` is a deliberate answer, not an absence."""
    source = """
        Button {
            act()
        } label: {
            Image(systemName: "star")
        }
        .accessibilityHidden(true)
"""
    assert not guard._is_icon_only_button(_chain(source))


# ---------------------------------------------------------------------------
# The empty allowlist removed the scanner's own proof of life
# ---------------------------------------------------------------------------


def test_the_blindness_floor_fires_when_the_detector_matches_nothing():
    """A broken matcher must exit 2, not report a clean tree.

    While the allowlist held entries, a non-empty result was itself evidence
    the reader worked. Now that every control is labelled, "all clean" and
    "matched nothing" print the same line — so the floor is asserted directly.

    The violation is synthesised here by breaking the reader, not by deleting
    files: a guard's self-test has to produce the failure it claims to catch.
    """
    import pytest

    original = guard._is_icon_only_button
    seen = guard.BUTTONS_SEEN
    try:
        guard.BUTTONS_SEEN = 0  # what a matcher that never fired leaves behind
        with pytest.raises(SystemExit) as exit_info:
            guard._require_buttons_seen_4382()
        assert exit_info.value.code == 2, "blindness is exit 2, never 0 or 1"
    finally:
        guard.BUTTONS_SEEN = seen
        guard._is_icon_only_button = original


def test_the_floor_passes_on_the_real_tree():
    """And it must NOT fire in normal operation, or it is just noise.

    A guard that cries blind on a healthy tree gets disabled within a week,
    which is the same outcome as not having written it.
    """
    guard.scan()

    assert guard.BUTTONS_SEEN >= guard.MIN_BUTTONS_SEEN, (
        f"only {guard.BUTTONS_SEEN} Button chains found in the real tree — "
        "either the detector regressed or the floor is set too high"
    )
