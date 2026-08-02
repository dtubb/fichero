import XCTest

@testable import Fichero

/// #4401, second instance: the library header re-imported internal drags.
///
/// The row path was fixed by identifying an internal drag POSITIVELY, by the
/// `doc:` id it carries. The library-section header was a separate
/// implementation of the same behaviour and did not get the fix — it carried
/// TWO drop modifiers on one view:
///
///     .onDrop(of: [UTType.fileURL]) { ... importFiles ... }
///     .dropDestination(for: SidebarDragID.self) { ... move ... }
///
/// Since #4123 an internal DOCUMENT drag vends a real file for cross-app
/// export, so it satisfies `canLoadObject(ofClass: URL.self)` and matched the
/// IMPORT handler. A document dragged onto the library header to move it to the
/// root was re-ingested as a brand-new document instead: a second, hollow copy
/// with no entities and no content — the exact data-loss shape of #4401.
///
/// Folders were unaffected, which is the tell that identifies the mechanism:
/// `SidebarDragID` only populates `documentId` for non-folders, so a folder row
/// exports no file, never matched the import handler, and moved correctly. Any
/// explanation that does not account for "folders were fine" is the wrong one.
///
/// These tests pin the ROUTING for the payload shapes each surface really sees.
/// The classifier is pure, so both the row and the header are covered by it —
/// which is the point of there being one classifier again.
final class LibraryHeaderDropRoutingTests: XCTestCase {

    // MARK: - The regression itself

    /// A transcribed document dragged inside the app: it advertises a file URL
    /// (the #4123 export) AND its own id. The id must win.
    func testInternalDocumentDragThatAlsoVendsAFileIsAMoveNotAnImport() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:11111111-2222-3333-4444-555555555555"],
            hasFileURL: true,
            carriesOwnProcessFlavor: true
        )

        XCTAssertEqual(
            payload,
            .internalItems(["doc:11111111-2222-3333-4444-555555555555"]),
            "an internal drag must move even when it also advertises a file (#4401)"
        )
    }

    /// The pre-fix behaviour, stated as the thing that must not come back: a
    /// file URL alone used to be enough to route to import.
    func testAFileURLAloneDoesNotOverrideAnInternalID() {
        guard case .internalItems = classifySidebarDropPayload(
            loadedIDs: ["some transcript text", "doc:abcd-1234"],
            hasFileURL: true,
            carriesOwnProcessFlavor: true
        ) else {
            return XCTFail("an id anywhere in the payload must route to move")
        }
    }

    /// A genuine Finder drag: no internal flavour, no id, just a file.
    func testFinderFileDragStillImports() {
        XCTAssertEqual(
            classifySidebarDropPayload(
                loadedIDs: [],
                hasFileURL: true,
                carriesOwnProcessFlavor: false
            ),
            .externalFiles
        )
    }

    /// Started inside the app, nothing readable. Importing would create the
    /// hollow duplicate; refusing loudly is the only safe answer.
    func testInternalDragWithNoReadableIDRefusesRatherThanImporting() {
        XCTAssertEqual(
            classifySidebarDropPayload(
                loadedIDs: ["Marshall diary transcript, 1893…"],
                hasFileURL: true,
                carriesOwnProcessFlavor: true
            ),
            .unreadableInternal,
            "re-ingesting something already in the library is the #4401 data loss"
        )
    }

    /// The id shape a Finder drag can never produce.
    func testOnlyDocPrefixedIDsCountAsInternal() {
        XCTAssertTrue(isInternalSidebarItemID("doc:abc"))
        XCTAssertFalse(isInternalSidebarItemID("doc:"), "a bare prefix is not an id")
        XCTAssertFalse(isInternalSidebarItemID("/Users/ann/Diary.pdf"))
        XCTAssertFalse(isInternalSidebarItemID("search:abc"))
    }

    // MARK: - One implementation, not two

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Sidebar
            .deletingLastPathComponent()   // Views
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    /// The header must not go back to two drop modifiers. Which one wins when
    /// both sit on the same view is not answerable from source, and it was
    /// load-bearing for whether a move became a copy.
    func testLibraryHeaderHasExactlyOneDropModifier() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarSectionHeader.swift")

        // Comment lines are excluded deliberately: the header's own doc comment
        // NAMES the two modifiers it used to have, and a guard that counted
        // those would fail on the explanation of the bug rather than on the bug.
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertEqual(
            code.components(separatedBy: ".onDrop(").count - 1,
            1,
            "the library header must have ONE drop handler (#4401)"
        )
        XCTAssertFalse(
            code.contains(".dropDestination(for: SidebarDragID.self"),
            "a second drop modifier on the header is what routed moves into imports"
        )
    }

    /// And that one handler must route by the shared classifier, not by
    /// capability. A `canLoadObject(ofClass: URL.self)` filter deciding the
    /// ROUTE is the original defect written out again.
    func testLibraryHeaderRoutesThroughTheSharedClassifier() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarSectionHeader.swift")
        XCTAssertTrue(source.contains("classifySidebarDropPayload("))
        XCTAssertTrue(source.contains("sidebarDropMightCarryInternalID("))
    }

    /// The header accepted the drop synchronously, so a refusal it cannot
    /// report is an item that appears to vanish.
    func testLibraryHeaderCanReportARefusedDrop() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarSectionHeader.swift")
        XCTAssertTrue(source.contains("onDropError"))

        let callSite = try Self.appSource("Views/Sidebar/Sections/SidebarView+LibraryHeaderHelpers.swift")
        XCTAssertTrue(
            callSite.contains("onDropError: { sidebarState.dropErrorMessage = $0 }"),
            "the error sink must be wired to the same banner every other drop failure uses"
        )
    }
}
