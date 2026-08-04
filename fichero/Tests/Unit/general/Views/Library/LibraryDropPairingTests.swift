@testable import Fichero
import XCTest

/// Every drag-source × drop-target pairing for a library item, pinned (#4474/#4475).
///
/// The defect was not two bugs. It was two payload types and two modifier
/// grammars encoding one concept, with nothing forcing them to agree:
///
///   - the sidebar vends `SidebarDragID` (`doc:<uuid>`), the library pane vends
///     `LibraryItemDrag` (JSON). The library folder cell was
///     `.dropDestination(for: LibraryItemDrag.self)` — TYPED — so a sidebar row
///     dropped on it matched nothing and did nothing at all: no move, no
///     feedback, no error (#4474);
///   - the sidebar implements Finder's grammar (⌥ copy, ⌘⌥ alias) and the
///     library cell always moved, so the same gesture on the same objects obeyed
///     two rules depending on which pane you did it in (#4475 B).
///
/// The unification is on the READING side. `classifySidebarDropPayload` is now
/// the one resolver both surfaces call, and `sidebarDropOperation` the one
/// grammar. The drag SOURCES are deliberately unchanged — teaching
/// `LibraryItemDrag` to vend `doc:` first would fix the cell and break chat,
/// which reads the first string representation. Changing a source to satisfy one
/// destination is how #4123 caused #4401.
///
/// The first two groups are real behaviour on pure functions. The wiring group
/// is source-shaped because "which drop API this view uses" is not observable
/// without a GUI — so each of those assertions is paired with an assertion that
/// the PRE-FIX shape is gone, which is what makes them fire rather than pass
/// vacuously over an unchanged file.
final class LibraryDropPairingTests: XCTestCase {

    private let docUUID = "11111111-2222-3333-4444-555555555555"

    private var sourceRoot: URL {
        get throws { try AppSource.root() }
    }

    private func source(_ path: String) throws -> String {
        try String(contentsOf: sourceRoot.appendingPathComponent(path), encoding: .utf8)
    }

    private func libraryDragJSON(kind: LibraryItemDrag.Kind, id: String) throws -> String {
        let drag = LibraryItemDrag(
            kind: kind, id: id, documentId: id, text: "some transcript"
        )
        return String(data: try JSONEncoder().encode(drag), encoding: .utf8)!
    }

    // MARK: - One payload concept: every in-app source resolves to the same thing

    /// PAIRING 1 — sidebar row → library folder cell (#4474, the reported bug).
    ///
    /// The cell now reads through this resolver, so a `doc:`-prefixed id
    /// arriving from the sidebar produces internal items instead of matching
    /// nothing. Before the fix the cell's typed destination never saw this
    /// payload at all and the drop silently ended.
    func testSidebarRowPayloadResolvesToAnInternalMove() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:\(docUUID)"],
            hasExternalPayload: true,          // #4123: internal document drags DO vend a file
            carriesOwnProcessFlavor: true
        )
        XCTAssertEqual(payload, .internalItems(["doc:\(docUUID)"]))
    }

    /// PAIRING 2 — library item → library folder cell, and → sidebar folder.
    /// The JSON shape must resolve to the SAME `doc:`-prefixed id the sidebar
    /// shape does, so nothing downstream can tell which pane the drag started in.
    func testLibraryItemPayloadResolvesToTheSameInternalShape() throws {
        for kind in [LibraryItemDrag.Kind.document, .page, .group] {
            let payload = classifySidebarDropPayload(
                loadedIDs: [try libraryDragJSON(kind: kind, id: docUUID)],
                hasExternalPayload: true,
                carriesOwnProcessFlavor: true
            )
            XCTAssertEqual(
                payload, .internalItems(["doc:\(docUUID)"]),
                "\(kind) must resolve to the same internal id shape as a sidebar row"
            )
        }
    }

    /// Both shapes in ONE drop resolve together — the mixed case that exists
    /// precisely because there are two sources.
    func testMixedSidebarAndLibraryPayloadsResolveTogether() throws {
        let other = "99999999-8888-7777-6666-555555555555"
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:\(docUUID)", try libraryDragJSON(kind: .document, id: other)],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: true
        )
        XCTAssertEqual(payload, .internalItems(["doc:\(docUUID)", "doc:\(other)"]))
    }

    /// Artifacts, notes and annotations are not documents and must never be
    /// reparented by a folder drop — the exclusion the old `moveDraggedItems`
    /// made by hand, now made once in the shared resolver.
    func testNonDocumentLibraryKindsAreNotReparented() throws {
        for kind in [LibraryItemDrag.Kind.artifact, .note, .annotation] {
            let payload = classifySidebarDropPayload(
                loadedIDs: [try libraryDragJSON(kind: kind, id: docUUID)],
                hasExternalPayload: false,
                carriesOwnProcessFlavor: true
            )
            XCTAssertNotEqual(
                payload, .internalItems(["doc:\(docUUID)"]),
                "\(kind) must not be treated as a movable document"
            )
        }
    }

    /// A genuine Finder drag still imports — the fix must not make every
    /// external drop look internal.
    func testExternalFileDragStillClassifiesAsExternal() {
        let payload = classifySidebarDropPayload(
            loadedIDs: [], hasExternalPayload: true, carriesOwnProcessFlavor: false
        )
        XCTAssertEqual(payload, .externalFiles)
    }

    /// An in-app drag whose id could not be read is REFUSED, never imported —
    /// re-ingesting something already in the library is the #4401 data loss.
    func testUnreadableInternalDragIsRefusedNotImported() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["just a transcript, no id"],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: true
        )
        XCTAssertEqual(payload, .unreadableInternal)
    }

    // MARK: - One modifier grammar

    /// PAIRING 3/4 — ⌥ and ⌘⌥ on a library folder cell. The cell resolves its
    /// operation through this function now; it used to hardcode a move, so
    /// these two pairings did the wrong thing rather than nothing.
    func testFinderGrammarForDocumentDrags() {
        let cases: [(option: Bool, command: Bool, expected: SidebarDropOperation)] = [
            (false, false, .move),
            (true,  false, .copy),
            (true,  true,  .alias),
            (false, true,  .move)   // ⌘ alone is not a copy modifier in Finder
        ]
        for testCase in cases {
            XCTAssertEqual(
                sidebarDropOperation(
                    optionHeld: testCase.option, commandHeld: testCase.command, kind: .document
                ),
                testCase.expected,
                "⌥=\(testCase.option) ⌘=\(testCase.command)"
            )
        }
    }

    /// Only documents have duplicate/alias endpoints; every other row kind
    /// moves whatever is held.
    func testNonDocumentKindsAlwaysMove() {
        for kind in [SidebarItemKind.savedSearch, .conversation, .workflow, .chain,
                     .schedule, .trigger, .folder, .unknown] {
            XCTAssertEqual(
                sidebarDropOperation(optionHeld: true, commandHeld: true, kind: kind),
                .move,
                "\(kind) has no duplicate/alias endpoint"
            )
        }
    }

    // MARK: - Failures are reported, not merely logged

    /// A cell drop that fails must produce a user-visible message. The old
    /// `moveDraggedItems` logged failures and returned true, so a refused move
    /// looked exactly like one that worked.
    func testFailedCellDropProducesAMessage() {
        XCTAssertNil(libraryCellDropOutcomeMessage(attempted: 3, failures: []))

        let allFailed = libraryCellDropOutcomeMessage(attempted: 1, failures: ["Locked."])
        XCTAssertNotNil(allFailed)
        XCTAssertTrue(allFailed!.contains("Locked."), "the reason must survive into the message")

        let partial = libraryCellDropOutcomeMessage(attempted: 3, failures: ["Locked."])
        XCTAssertNotNil(partial)
        XCTAssertTrue(partial!.contains("1 of 3"), "partial failure must say how many: \(partial!)")
    }

    // MARK: - Wiring (each paired with the pre-fix shape it replaced)

    /// The library folder cell must read drops through the shared reader, and
    /// must NO LONGER be typed on `LibraryItemDrag` — the typed destination IS
    /// the #4474 bug, so its absence is what proves this assertion fires.
    func testFolderCellUsesTheSharedReaderAndIsNoLongerTyped() throws {
        let cell = try source("Views/Library/ViewModes/LibraryView+CellDrop.swift")

        XCTAssertFalse(
            cell.contains(".dropDestination(for: LibraryItemDrag.self)"),
            "the typed destination is the bug: it matches sidebar drags not at all"
        )
        XCTAssertFalse(
            cell.contains("func moveDraggedItems"),
            "the always-moves executor must be gone, not merely bypassed"
        )
        XCTAssertTrue(cell.contains("readSidebarDropPayload"), "reads via the shared reader")
        XCTAssertTrue(
            cell.contains("sidebarDropOperation(modifiers:"),
            "resolves ⌥/⌘⌥ through the shared grammar"
        )
        XCTAssertTrue(
            cell.contains("applyLibraryItemDropOperation"),
            "applies through the shared executor, not a private move"
        )
    }

    /// All four library view modes route through the one modifier, so the fix
    /// cannot cover list and miss columns.
    func testEveryLibraryViewModeRoutesThroughTheSharedCellDrop() throws {
        let modes = [
            "Views/Library/ViewModes/LibraryView+ListView.swift",
            "Views/Library/ViewModes/LibraryView+IconMode.swift",
            "Views/Library/ViewModes/LibraryView+TableColumns.swift",
            "Views/Library/ViewModes/Columns/LibraryView+ColumnsView.swift"
        ]
        for path in modes {
            let code = try source(path)
            XCTAssertTrue(code.contains("LibraryFolderCellDrop("), path)
            XCTAssertTrue(
                code.contains("handleFolderCellDrop(providers"),
                "\(path) must use the unified handler"
            )
            XCTAssertFalse(
                code.contains("moveDraggedItems("),
                "\(path) must not keep calling the always-moves executor"
            )
        }
    }

    /// Every surface that accepts an in-app item drag reads it the same way.
    /// Three hand-rolled copies of this plumbing existed; a copied classifier is
    /// how the library header got a divergent routing rule in the first place.
    func testAllInAppDropSurfacesShareOneReader() throws {
        let surfaces = [
            "Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift",
            "Views/Sidebar/Sections/SidebarSectionHeader.swift",
            "Views/Library/ViewModes/LibraryView+CellDrop.swift"
        ]
        for path in surfaces {
            let code = try source(path)
            XCTAssertTrue(code.contains("readSidebarDropPayload"), path)
            // The private string-loading helper, not the `canLoadObject`
            // capability probe — the row path legitimately still probes.
            XCTAssertFalse(
                code.contains("func loadString("),
                "\(path) must not keep a private copy of the string-loading plumbing"
            )
        }
    }

    /// #4475 C — modifier state is sampled ONCE per drop, at the entry point.
    ///
    /// Two functions re-reading live modifier flags at different instants is the
    /// "two things nothing forces to agree" shape this whole family is made of.
    /// They agreed by luck; now the sampled value is threaded down instead.
    func testModifiersAreSampledOnlyAtDropEntryPoints() throws {
        // Each drop entry point samples exactly once. `handleNestedInsertionDrop`
        // is the only sampler in this file now — `handleNonMoveInsertion` takes
        // what it is given.
        let rowDrop = try source("Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift")
        XCTAssertEqual(
            rowDrop.components(separatedBy: "SidebarDropModifiers.current()").count - 1, 1,
            "exactly one sampling site: the drop entry point"
        )
        XCTAssertTrue(
            rowDrop.contains("modifiers: SidebarDropModifiers"),
            "the sampled value is passed down, not re-read"
        )
        XCTAssertFalse(
            rowDrop.contains("sidebarDropOperation(modifiers: .current()"),
            "no operation is resolved from a fresh live read below the entry point"
        )

        let unifiedRows = try source("Views/Sidebar/Sections/SidebarView+UnifiedRows.swift")
        XCTAssertEqual(
            unifiedRows.components(separatedBy: "SidebarDropModifiers.current()").count - 1, 1,
            "exactly one sampling site: the drop entry point"
        )
        XCTAssertFalse(unifiedRows.contains("sidebarDropOperation(modifiers: .current()"))

        // The folder-cell entry point samples once too.
        let cell = try source("Views/Library/ViewModes/LibraryView+CellDrop.swift")
        XCTAssertEqual(
            cell.components(separatedBy: ".current()").count - 1, 1,
            "the cell samples once, in handleFolderCellDrop"
        )
    }

    /// A failed cell drop must reach a rendered surface. Writing to a field
    /// nothing displays would be the same silent-failure defect in a new place.
    func testCellDropErrorsReachARenderedAlert() throws {
        let cell = try source("Views/Library/ViewModes/LibraryView+CellDrop.swift")
        XCTAssertTrue(cell.contains("windowState.dropErrorMessage ="))
        XCTAssertTrue(
            cell.contains("struct LibraryDropAlertModifier"),
            "the message must have a presenter"
        )
        let libraryView = try source("Views/Library/LibraryView.swift")
        XCTAssertTrue(
            libraryView.contains("LibraryDropAlertModifier(windowState:"),
            "the presenter must actually be applied to the library body"
        )
        let windowState = try source("Models/WindowState.swift")
        XCTAssertTrue(windowState.contains("var dropErrorMessage: String?"))
    }

    /// The drag SOURCES stay as they are. This is the constraint that blocked
    /// the obvious "just make both vend `doc:` first" fix: chat reads the FIRST
    /// string representation, so reordering `LibraryItemDrag` breaks it, and
    /// reordering was how #4123 caused #4401.
    func testDragSourcesWereNotReorderedToSuitOneDestination() throws {
        let document = try source("Models/Document.swift")
        XCTAssertTrue(
            document.contains("CodableRepresentation(contentType: .json)"),
            "LibraryItemDrag keeps JSON first"
        )
        let sidebarRow = try source("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        XCTAssertTrue(
            sidebarRow.contains("ProxyRepresentation(exporting: \\.id)"),
            "SidebarDragID keeps its id representation (first, per #4401)"
        )
    }
}
