"""Seam category 4 — focused values and commands (SwiftUI) (#4420).

The archetype is #4376: ``librarySelectAll`` was published with
``focusedSceneValue``, fully implemented, and consumed by NOBODY — ⌘A reached
no menu item and the mechanism was complete at both ends except for the wire.
The inverse also ships silently: a menu button reading a ``@FocusedValue``
nobody publishes renders permanently disabled, which looks identical to
"not applicable here" (#4419's family).

THE RULE, mechanically — for every key declared on ``extension
FocusedValues``:

    declared  ⇒  published somewhere  AND  read somewhere
    published ⇒  declared             (a typo'd keypath does not compile,
                                       so this direction is structural)
    read      ⇒  published            (unless allowlisted with a reason)

Publishers are ``.focusedValue(\\.key, …)`` / ``.focusedSceneValue(\\.key,
…)``; readers are ``@FocusedValue(\\.key)`` / ``@FocusedBinding(\\.key)``.
Matching is whitespace-tolerant across newlines: the first measurement pass
used a single-line grep and reported TEN unpublished keys, all false — every
publisher in this codebase puts the keypath on its own line. Hand-checking
before claiming (the suite's convention) is what caught it.

Scope note, stated rather than papered over: the "every keyboard shortcut
reaches a handler" half of category 4 is structural for the pattern this
codebase uses — ``.keyboardShortcut`` is attached to ``Button``s whose action
IS the handler (the FocusedCommandButtons family), so a shortcut without a
handler cannot be expressed. What CAN break is the button's focused value
having no publisher, which is exactly what this sweep checks.

Findings are reported, not fixed (#4420).
"""

from __future__ import annotations

import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[4] / "fichero" / "fichero"

_LINE_COMMENT = re.compile(r"//.*")
_PUBLISH = re.compile(r"\.focused(?:Scene)?Value\(\s*\\\.(\w+)", re.S)
_READ = re.compile(r"@Focused(?:Value|Binding)\(\s*\\\.(\w+)", re.S)
_DECL_BLOCK = re.compile(r"extension FocusedValues\s*\{(.*?)\n\}", re.S)
_DECL_VAR = re.compile(r"var\s+(\w+)\s*:")

# Keys allowed to be PUBLISHED but not read, each with the reason. The list is
# bidirectionally hygienic: if a reader appears for a listed key, the entry is
# stale and the sweep fails until it is removed.
ALLOWED_UNREAD: dict[str, str] = {
    "libraryDeleteSelection": (
        "deliberately unread — reading it from ContentView closed an infinite "
        "invalidation loop (~97% CPU at idle) because the closure is re-allocated "
        "every body pass; see the #2032 note in ContentView.swift. Re-adding a "
        "reader requires an Equatable action wrapper first."
    ),
}

# Keys allowed to be READ but not published, each with the reason. Empty: a
# reader without a publisher is a permanently disabled control.
ALLOWED_UNPUBLISHED: dict[str, str] = {}


def _scan(root: Path) -> tuple[set[str], set[str], set[str], int]:
    """(declared, published, read, files_walked) over every .swift in root."""
    declared: set[str] = set()
    published: set[str] = set()
    read: set[str] = set()
    files = 0
    for path in root.rglob("*.swift"):
        files += 1
        text = _LINE_COMMENT.sub("", path.read_text(encoding="utf-8"))
        published.update(_PUBLISH.findall(text))
        read.update(_READ.findall(text))
        for block in _DECL_BLOCK.findall(text):
            declared.update(_DECL_VAR.findall(block))
    return declared, published, read, files


def _real_tree() -> tuple[set[str], set[str], set[str], int]:
    declared, published, read, files = _scan(APP_ROOT)
    # Guard the guard (#4382): a sweep that walked nothing must fail, not pass.
    assert files >= 500, f"only {files} Swift files walked under {APP_ROOT}"
    assert len(declared) >= 20, (
        f"only {len(declared)} FocusedValues keys discovered — the declaration "
        "pattern moved and this sweep is measuring almost nothing"
    )
    return declared, published, read, files


def test_every_declared_focused_value_is_published():
    declared, published, _, _ = _real_tree()
    unpublished = sorted(declared - published - set(ALLOWED_UNPUBLISHED))
    assert unpublished == [], (
        "focused-value keys declared and (via their readers) rendered as "
        "commands, but PUBLISHED by no view — the reading control is "
        "permanently disabled and indistinguishable from 'not applicable' "
        f"(#4376 family): {unpublished}"
    )


def test_every_declared_focused_value_is_read():
    declared, _, read, _ = _real_tree()
    unread = sorted(declared - read - set(ALLOWED_UNREAD))
    assert unread == [], (
        "focused-value keys published by a view but READ by nothing — a "
        "complete mechanism with no consumer, the exact #4376 shape: "
        f"{unread}"
    )


def test_every_read_key_has_a_publisher():
    _, published, read, _ = _real_tree()
    orphaned = sorted(read - published - set(ALLOWED_UNPUBLISHED))
    assert orphaned == [], (
        "@FocusedValue readers whose key is never published anywhere: "
        f"{orphaned}"
    )


def test_the_allowlists_are_not_stale():
    """Bidirectional hygiene: an entry whose condition healed must go."""
    _, published, read, _ = _real_tree()
    stale_unread = sorted(k for k in ALLOWED_UNREAD if k in read)
    stale_unpublished = sorted(k for k in ALLOWED_UNPUBLISHED if k in published)
    assert stale_unread == [], (
        f"ALLOWED_UNREAD entries that now HAVE a reader — remove them (and "
        f"check the #2032 invalidation-loop condition first): {stale_unread}"
    )
    assert stale_unpublished == [], (
        f"ALLOWED_UNPUBLISHED entries that now have a publisher: {stale_unpublished}"
    )


class TestTheSweepItselfFires:
    """Drive the check (#4382's lesson): prove each rule trips on a synthetic
    tree containing exactly the defect it hunts, so a regex regression cannot
    quietly blind the sweep."""

    @staticmethod
    def _write(tmp_path: Path, name: str, text: str) -> None:
        (tmp_path / name).write_text(text)

    def test_detects_a_published_but_unread_key(self, tmp_path):
        self._write(
            tmp_path,
            "Keys.swift",
            "extension FocusedValues {\n    var orphanAction: (() -> Void)?\n}\n",
        )
        self._write(
            tmp_path,
            "Publisher.swift",
            "struct P: View { var body: some View { EmptyView()"
            ".focusedSceneValue(\n    \\.orphanAction,\n    nil) } }\n",
        )
        declared, published, read, _ = _scan(tmp_path)
        assert "orphanAction" in declared and "orphanAction" in published
        assert "orphanAction" not in read, "the defect this test seeds was not seeded"
        assert declared - read == {"orphanAction"}

    def test_detects_a_read_but_unpublished_key(self, tmp_path):
        self._write(
            tmp_path,
            "Reader.swift",
            "struct R: View {\n"
            "    @FocusedValue(\\.ghostAction) private var ghost\n"
            "    var body: some View { EmptyView() }\n}\n",
        )
        _, published, read, _ = _scan(tmp_path)
        assert read - published == {"ghostAction"}

    def test_multiline_publishers_are_seen(self, tmp_path):
        """The false-positive class the first measurement hit: keypath on its
        own line. If this regresses, ten real publishers disappear at once."""
        self._write(
            tmp_path,
            "Multiline.swift",
            "struct M: View { var body: some View { EmptyView()\n"
            "    .focusedSceneValue(\n"
            "        \\.wrappedKey,\n"
            "        nil\n"
            "    ) } }\n",
        )
        _, published, _, _ = _scan(tmp_path)
        assert "wrappedKey" in published

    def test_commented_out_publishers_are_not_counted(self, tmp_path):
        self._write(
            tmp_path,
            "Commented.swift",
            "// .focusedSceneValue(\\.deadKey, nil)\n",
        )
        _, published, _, _ = _scan(tmp_path)
        assert "deadKey" not in published
