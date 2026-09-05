@testable import Fichero
import Foundation
import XCTest

/// `LibraryManager.shared.globalLibrary` is the library holding the RESERVED
/// id — not "the library this window is showing". A surface that reaches for
/// it while the user is in another library gets *a* real answer from the wrong
/// scope: no error, no empty state, just facts about a different database.
///
/// The class has been met four times now — #4306 (translate ran against the
/// global library's actions service), #4461 (the KG web pane), and on
/// 2026-09-04 the reader's Node Graph, the map and the timeline in one
/// afternoon. Fix-then-sweep: this file is what stops a fifth.
///
/// It does NOT ban the symbol. Plenty of reads are correct — an app-level
/// setting, an Intent with no window, a `?? globalLibrary` fallback after a
/// `windowState.libraryId` lookup, and the workflow picker's documented
/// global-defaults fallback (#4450). What it bans is a PRIMARY read in a
/// surface that is scoped to a document, an entity or a claim.
@MainActor
final class OwningLibraryScopeTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// A read that is NOT a `??` fallback and not a comment — the shape that
    /// makes the global library a surface's only answer.
    private static func primaryReads(in source: String) -> [String] {
        source
            .components(separatedBy: .newlines)
            .filter { line in
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                guard trimmed.contains("globalLibrary"), !trimmed.contains("globalLibraryId") else {
                    return false
                }
                // Comments discuss the defect; they are not the defect.
                guard !trimmed.hasPrefix("//"), !trimmed.hasPrefix("///") else { return false }
                // `x ?? globalLibrary` is the sanctioned fallback shape.
                return !trimmed.contains("?? libraryManager.globalLibrary")
                    && !trimmed.contains("?? LibraryManager.shared.globalLibrary")
            }
    }

    /// The surfaces fixed on 2026-09-04. Each of these asked the global
    /// library for entities or claims belonging to a document the user was
    /// reading in a different one, and each came back empty or wrong.
    private static let cleanedSurfaces = [
        "Views/Library/ViewModes/Graph/KGMapView.swift",
        "Views/Library/ViewModes/Graph/KGTimelineView.swift",
        "Views/Library/ViewModes/Graph/Ontology/ForceDirectedGraphView.swift",
        // Shapes B and C, 2026-09-04: the last runtime reads in the browser.
        "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift",
        "Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift",
        "Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Biography.swift",
        "Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Metadata.swift"
    ]

    func testTheFixedSurfacesDoNotReacquireTheGlobalLibrary() throws {
        for path in Self.cleanedSurfaces {
            let reads = Self.primaryReads(in: try Self.appSource(path))
            XCTAssertTrue(
                reads.isEmpty,
                """
                \(path) reads globalLibrary as a primary source again: \
                \(reads.map { $0.trimmingCharacters(in: .whitespaces) }). \
                Take the surface's own service from the environment instead.
                """
            )
        }
    }

    /// The Ontology browser's sheets and toolbars still resolve the global
    /// library to MUTATE entities and claims — merge, split, create, triage,
    /// audit. That is worse than the read-only surfaces above: a merge
    /// executed against the wrong database is not an empty view, it is a write
    /// somewhere the user was not looking.
    ///
    /// They are not fixed here because none of them holds an injected service
    /// to resolve their library from — the fix is to thread one in and use
    /// `LibraryManager.library(owningService:)`, which exists for exactly this
    /// and matches by object identity so it cannot drift.
    ///
    /// AT THE FLOOR. Every runtime read is gone; the two that remain are
    /// `#Preview` scaffolding in `OntologyBrowser.swift`
    /// (`.environment(LibraryManager.shared.globalLibrary!.claimStore)` and
    /// its sibling), which never runs in the app. They are deliberately NOT
    /// "fixed": preview code wants a concrete library to build a preview
    /// with, and changing it to make a number look better would be the number
    /// leading the code.
    ///
    /// EQUALITY, not `<=`, now that it is exact: a drop to 1 or 0 means
    /// somebody edited the previews, which is worth a failing test asking
    /// why — and a rise means a runtime read came back.
    func testTheOntologyBrowserHasNoRuntimeGlobalLibraryReadsLeft() throws {
        let root = try AppSource.root().appendingPathComponent(
            "Views/Library/ViewModes/Graph/Ontology"
        )
        let files = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        )?.compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" } ?? []
        XCTAssertFalse(files.isEmpty, "The Ontology directory moved; this ratchet is measuring nothing.")

        var total = 0
        for file in files {
            let source = try String(contentsOf: file, encoding: .utf8)
            total += Self.primaryReads(in: source).count
        }
        XCTAssertEqual(
            total, 2,
            """
            The Ontology browser's runtime `globalLibrary` reads are all gone; \
            the only two matches left are #Preview scaffolding. More than 2 \
            means a runtime read came back — that surface is per-library, so \
            resolving the RESERVED-id library there reads, or writes, \
            somebody else's graph. Fewer than 2 means the previews changed, \
            which is fine but should be deliberate.
            """
        )
    }

    /// Every mutating path reads the INJECTED service and carries no fallback
    /// tail. The tail is the regression that matters: re-adding
    /// `?? LibraryManager.shared.globalLibrary` to make a nil go away would
    /// restore the bug while looking like a robustness fix.
    func testTheMutatingPathsUseTheInjectedService() throws {
        let paths = [
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntitySplitSheet.swift",
            "Views/Library/ViewModes/Graph/Ontology/Entity/NewEntitySheet.swift",
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntitySourceGroupsView.swift",
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Audit.swift",
            "Views/Library/ViewModes/Graph/Ontology/Claim/ContradictionTriageSheet.swift",
            "Views/Library/ViewModes/Graph/Ontology/OntologyBrowser+Toolbar.swift",
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift"
        ]
        for path in paths {
            let source = try Self.appSource(path)
            XCTAssertTrue(
                Self.primaryReads(in: source).isEmpty,
                "\(path) resolves the global library again"
            )
            XCTAssertFalse(
                source.contains("?? LibraryManager.shared.globalLibrary"),
                """
                \(path) grew a global-library fallback. A surface that cannot \
                name the library it is about to change must fail visibly, not \
                guess one — the fallback IS the defect, wearing a fix's clothes.
                """
            )
        }
    }

    /// A sheet that cannot name its library says so where the user is looking,
    /// rather than returning silently and leaving a spinner or a dead button.
    func testASheetWithNoServiceSaysSoRatherThanFailingSilently() throws {
        let split = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntitySplitSheet.swift"
        )
        let new = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Entity/NewEntitySheet.swift"
        )
        XCTAssertTrue(split.contains("errorText = \"This window has no library to split the entity in.\""))
        XCTAssertTrue(new.contains("errorText = \"This window has no library to create the entity in.\""))
    }

    /// MERGE is the verb Daniel's dedupe program is built on, and it is a
    /// WRITE — the one path where the wrong library is not an empty view but
    /// a change to somebody else's graph. It resolves the library by object
    /// identity from the service it was handed, and says so when it cannot.
    func testMergeNamesTheLibraryItIsAboutToChange() throws {
        let merge = try Self.appSource(
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntityMergeSheet.swift"
        )
        XCTAssertTrue(merge.contains("LibraryManager.shared.library(owningService: $0)"))
        XCTAssertTrue(
            merge.contains("errorText = \"This window has no library to merge the entities in.\"")
        )
    }

    /// The identity contract the whole fix rests on: a service the library
    /// vended resolves to that library, and one it did not vend resolves to
    /// NIL — never to a plausible other library. Asserted directly rather
    /// than inferred from the surfaces that depend on it.
    func testOwningServiceResolvesByIdentityAndFailsToNil() {
        let stranger = EntitySearchState()
        XCTAssertNil(
            LibraryManager.shared.library(owningService: stranger),
            """
            An object no library vended must resolve to nil. Falling back to \
            a library here is exactly the defect: the caller would proceed, \
            confidently, against a graph it cannot name.
            """
        )
    }
}
