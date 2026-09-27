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
because that is the case the guard exists for (#5110 named three; all have since been wired
or deleted, so that proof now runs on a synthetic tree).
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

    #: Built-but-unreachable when this file was written (#5110). `FirstRunWindow+Library.swift`
    #: turned out to be debris and was deleted; the two sheets were given a door from the
    #: entity table's context menu by 1174ea412 (EntitiesLibraryContent.swift). The guard moved
    #: on its own — both stopped being reported — and the old assertion here, that they were
    #: STILL reported, went red because the code got wired. A test pinning a real file as
    #: dead fails every time somebody fixes what the guard complains about, so the "hatch is
    #: not too wide" proof now runs on a synthetic tree nobody can wire
    #: (`TestTheScanStillReportsAnUnpresentedView`).
    NOW_WIRED = (
        "Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift",
        "Views/Library/ViewModes/Graph/Ontology/Entity/EntitySplitSheet.swift",
    )

    def test_the_sheets_given_a_door_are_neither_reported_nor_backlogged(self):
        """A wired file left in KNOWN_VIOLATIONS makes the backlog a list of excuses that
        outlive their reason; a wired file still reported means the scan stopped seeing
        presentation sites."""
        found = dead.scan()
        for rel in self.NOW_WIRED:
            assert rel not in found, rel
            assert rel not in dead.KNOWN_VIOLATIONS, rel

    def test_the_deleted_row_is_gone_from_the_tree_and_the_backlog(self):
        """A deleted file must leave no seeded entry behind, or the backlog outlives the file."""
        rel = "Views/Onboarding/FirstRunWindow+Library.swift"
        assert not (dead.SWIFT_ROOT / rel).exists()
        assert rel not in dead.KNOWN_VIOLATIONS

    def test_no_backlog_entry_outlives_its_file_being_wired(self):
        """The guard only PRINTS stale entries ("clean them up when convenient"), so they
        never got cleaned: `Models/SegmentSelection.swift` was built ahead of its consumers,
        entered here, and wired by the next merge (54ca8b1e5) — the entry would have sat
        excusing nothing. A backlog that keeps excuses for live code cannot be read as a
        list of what is actually dead."""
        stale = sorted(set(dead.KNOWN_VIOLATIONS) - set(dead.scan()))
        assert stale == [], f"drop from KNOWN_VIOLATIONS, these are no longer dead: {stale}"

    def test_the_allowlist_shrank_past_the_blind_spot(self):
        """50 entries, 27 of them one missing rule. A guard whose allowlist is half
        workaround is measuring its own blind spot, not the codebase."""
        assert len(dead.KNOWN_VIOLATIONS) < 30


def _scan_tree(tmp_path, monkeypatch, files: dict[str, str]) -> dict[str, list[str]]:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    monkeypatch.setattr(dead, "SWIFT_ROOT", tmp_path)
    return dead.scan()


class TestTheScanStillReportsAnUnpresentedView:
    """Whole-scan proof that the extension hatch did not go too wide.

    It used to lean on two real sheets staying unreachable; they were wired the same day and
    the test went red for doing its job. A synthetic tree cannot be wired by another lane.
    """

    def test_a_self_contained_view_nobody_presents_is_reported(self, tmp_path, monkeypatch):
        """`merge()` is called elsewhere, but the orphan has no extension block, so the hatch
        must not excuse it. If this fails, every unpresented sheet in the app goes silent."""
        found = _scan_tree(tmp_path, monkeypatch, {
            "Views/OrphanSheet.swift": (
                "struct OrphanSheet: View {\n"
                "    var body: some View { Text(\"x\") }\n"
                "    func merge() {}\n"
                "}\n"
            ),
            "Views/Host.swift": (
                "struct Host: View {\n"
                "    var body: some View { Button(\"m\") { merge() } }\n"
                "}\n"
            ),
        })
        assert "Views/OrphanSheet.swift" in found

    def test_the_same_view_once_presented_is_not_reported(self, tmp_path, monkeypatch):
        """Over-fire check: naming the type from another file is exactly what wiring looks
        like, and a guard that still reports it teaches people to allowlist live code."""
        found = _scan_tree(tmp_path, monkeypatch, {
            "Views/OrphanSheet.swift": (
                "struct OrphanSheet: View {\n"
                "    var body: some View { Text(\"x\") }\n"
                "}\n"
            ),
            "Views/Host.swift": (
                "struct Host: View {\n"
                "    var body: some View { Color.clear.sheet(isPresented: .constant(true)) "
                "{ OrphanSheet() } }\n"
                "}\n"
            ),
        })
        assert "Views/OrphanSheet.swift" not in found
