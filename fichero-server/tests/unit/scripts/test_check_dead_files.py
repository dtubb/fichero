"""When check_dead_files may call a Swift file dead.

It had no test, and it read TYPE declarations only. A file whose whole job is to add methods to
somebody else's type declares no type anybody names — so it was reported dead while being
called every frame. That single blind spot accounted for **27 of its 50** allowlist entries,
each one reading some version of "extension file; scanner misses same-file extension wiring".
Two live files were still being reported on 2026-09-27:

    Views/Reader/Page/ReaderFolderProxy.swift
        folderProxy(for:) / folderProxyContent(_:) called from ReadingPaneView+Tabs.swift:97,107
    Views/Shell/ContentView/ContentView+SelectionAndDetailEvents.swift
        handleBrowserSelectionChange / handleDetailDocumentChange called from
        ContentView+RootLayout.swift:400,404

The escape hatch is deliberately narrow, and the second half of these tests is what keeps it
narrow: a self-contained `struct SomeSheet: View` that nothing presents must still be reported,
because that is the case the guard exists for (#5110 has three of them).
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_dead_files.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_dead_files", _SCRIPT)
assert _SPEC and _SPEC.loader
dead = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = dead
_SPEC.loader.exec_module(dead)  # type: ignore[attr-defined]


def _reached(source: str, *, elsewhere: str = "") -> bool:
    """Ask the rule directly: `source` is the file under test, `elsewhere` is the rest of the app."""
    own = Counter(dead.IDENTIFIER.findall(source))
    total = Counter(own)
    total.update(dead.IDENTIFIER.findall(elsewhere))
    return dead._reached_by_extension(source, own, total)


class TestAnExtensionFileIsReachedThroughItsMethods:
    def test_a_method_called_from_another_file_keeps_the_file_alive(self):
        source = """
extension ReadingPaneView {
    func folderProxy(for doc: Document) -> ReaderFolderProxy? { nil }
}
"""
        assert _reached(source, elsewhere="let proxy = folderProxy(for: doc)")

    def test_the_same_file_with_nobody_calling_it_is_not_excused(self):
        """The hatch is "somebody else calls it", not "it is an extension"."""
        source = """
extension ReadingPaneView {
    func folderProxy(for doc: Document) -> ReaderFolderProxy? { nil }
}
"""
        assert not _reached(source, elsewhere="nothing here calls it")

    def test_a_file_with_no_extension_block_is_never_excused(self):
        """A self-contained unreferenced view is the case this guard is FOR (#5110)."""
        source = """
struct EntityMergeSheet: View {
    var body: some View { Text("merge") }
    func merge() {}
}
"""
        assert not _reached(source, elsewhere="merge()")

    def test_a_protocol_requirement_does_not_count_as_being_called(self):
        """`body` is declared by every SwiftUI view, so a match on it says nothing.

        Without this exclusion the hatch would excuse essentially every view file in the app
        and the guard would report nothing at all.
        """
        source = """
extension SomeView {
    var body: some View { Text("x") }
    func body() {}
}
"""
        assert not _reached(source, elsewhere="view.body")

    def test_a_commented_out_method_is_not_a_declaration(self):
        """Prose is not code — the distinction #5108 and #5109 both turned on."""
        source = """
extension SomeView {
    // func folderProxy(for doc: Document) {}
}
"""
        assert not _reached(source, elsewhere="folderProxy(for: doc)")


class TestTheTwoLiveFilesAreNoLongerReported:
    def test_neither_extension_file_is_a_candidate(self):
        found = dead.scan()
        for rel in (
            "Views/Reader/Page/ReaderFolderProxy.swift",
            "Views/Shell/ContentView/ContentView+SelectionAndDetailEvents.swift",
        ):
            assert rel not in found, f"{rel} is live; its methods are called from another file"

    def test_the_three_built_but_unreachable_views_are_still_reported(self):
        """If these stop being reported the hatch has gone too wide, not the code got wired —
        a wiring would show up as the KNOWN_VIOLATIONS entry going stale instead (#5110)."""
        found = dead.scan()
        for rel in (
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift",
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntitySplitSheet.swift",
            "Views/Onboarding/FirstRunWindow+Library.swift",
        ):
            assert rel in found, rel

    def test_each_of_those_three_is_seeded_with_its_issue(self):
        for rel in (
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift",
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntitySplitSheet.swift",
            "Views/Onboarding/FirstRunWindow+Library.swift",
        ):
            assert "#5110" in dead.KNOWN_VIOLATIONS[rel], rel

    def test_the_allowlist_shrank_past_the_blind_spot(self):
        """50 entries, 27 of them one missing rule. A guard whose allowlist is half
        workaround is measuring its own blind spot, not the codebase."""
        assert len(dead.KNOWN_VIOLATIONS) < 30
