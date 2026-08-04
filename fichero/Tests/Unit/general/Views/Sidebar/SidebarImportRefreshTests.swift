import Foundation
import XCTest

/// #4522 — one import must not redraw the sidebar twice.
///
/// Every `DocumentStore.refresh()` ends in `loadCollections()`, which drops the
/// entire `childrenCache` and re-prefetches every root: a refresh is a
/// full-forest rebuild, not an update. Three import callers ran
/// `refresh(); sleep(500ms); refresh()` as "hardening" against the engine not
/// having finished indexing. #4067 deleted that from the row-drop path — the
/// engine emits a per-file `document.created` and the store patches
/// incrementally, so the sleep bought nothing and cost a visible second redraw
/// half a second after the import already looked done. Two callers were missed.
///
/// This is a SOURCE check, deliberately, and its limits are stated: a counting
/// test would need a live store, a live change stream and a real import, which
/// is an XCUITest. What is checkable here is the pattern itself, and the
/// pattern is what regrew. It scans the whole sidebar tree rather than the two
/// known files, because naming the files is how #4067's fix missed these.
final class SidebarImportRefreshTests: XCTestCase {

    /// True when `source` sleeps between two store refreshes — the exact shape
    /// #4067 removed. Static so the self-test can run the SAME matcher.
    static func hasSleepBetweenRefreshes(_ source: String) -> Bool {
        let pattern = #"documentStore\.refresh\(\)[\s\S]{0,400}?Task\.sleep[\s\S]{0,400}?documentStore\.refresh\(\)"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return false }
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        return regex.firstMatch(in: source, range: range) != nil
    }

    private func sidebarSources() throws -> [(path: String, text: String)] {
        let root = try AppSource.root().appendingPathComponent("Views/Sidebar")
        guard let walker = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        ) else {
            XCTFail("BLIND: could not enumerate \(root.path)")
            return []
        }
        var files: [(String, String)] = []
        for case let url as URL in walker where url.pathExtension == "swift" {
            files.append((url.lastPathComponent, try String(contentsOf: url, encoding: .utf8)))
        }
        return files
    }

    func testNoSidebarImportPathSleepsBetweenTwoRefreshes() throws {
        let files = try sidebarSources()
        // Floor: an empty or tiny walk would pass for the wrong reason.
        XCTAssertGreaterThan(
            files.count, 15,
            "BLIND: only \(files.count) sidebar sources found; the tree moved"
        )
        for file in files {
            XCTAssertFalse(
                Self.hasSleepBetweenRefreshes(file.text),
                """
                \(file.path): refresh + sleep + refresh is back. Each refresh \
                rebuilds the whole sidebar forest, so this redraws it twice for \
                one import (#4522). The engine's per-file document.created \
                events already patch the tree; one trailing refresh is the \
                completion signal (#4067).
                """
            )
        }
    }

    /// The matcher must be observed to fire, or the green above proves nothing.
    /// Synthesised rather than borrowed, so paying the debt cannot silently
    /// disarm it.
    func testMatcherCatchesTheExactPatternThatWasDeleted() {
        let violation = """
            await library.documentStore.refresh()
            try? await Task.sleep(for: .milliseconds(500))
            await library.documentStore.refresh()
            """
        XCTAssertTrue(Self.hasSleepBetweenRefreshes(violation))
    }

    func testMatcherAcceptsASingleTrailingRefresh() {
        let fixed = """
            await library.documentStore.refresh()
            if let message = outcome.partialFailureMessage { report(message) }
            """
        XCTAssertFalse(Self.hasSleepBetweenRefreshes(fixed))
    }

    /// The change-stream rebuild is the PRIMARY path and must survive: it is
    /// what makes an import from another window (or another client) appear
    /// here at all, and it is the lost-event backstop's partner. Deleting the
    /// two sleeps must not have taken it with them.
    func testTheChangeStreamRebuildIsStillWired() throws {
        let observers = try AppSource.text("Views/Sidebar/Components/SidebarObservers.swift")
        XCTAssertTrue(
            observers.contains("rebuildCaches(for: libraryId)"),
            "#4522 removed the redundant redraws, not the change-stream one"
        )
    }
}
