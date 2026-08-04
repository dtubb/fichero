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
            hasExternalPayload: true,
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
            hasExternalPayload: true,
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
                hasExternalPayload: true,
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
                hasExternalPayload: true,
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

    // MARK: - Two drag types for one concept (library pane -> sidebar)

    private func libraryDragJSON(
        kind: String = "document",
        id: String = "11111111-2222-3333-4444-555555555555",
        documentId: String? = "11111111-2222-3333-4444-555555555555",
        text: String = "Marshall diary, 1893…"
    ) -> String {
        let documentIdField = documentId.map { "\"documentId\":\"\($0)\"," } ?? "\"documentId\":null,"
        return """
        {"kind":"\(kind)","id":"\(id)",\(documentIdField)"text":"\(text)","name":"Diary.pdf"}
        """
    }

    /// The gesture this restores: drag a document out of the LIBRARY pane —
    /// where the documents actually are — onto a sidebar folder to file it.
    ///
    /// Library rows/tiles/columns/table cells vend `LibraryItemDrag`, whose `id`
    /// is the BARE document id and whose first string is JSON. Only the
    /// sidebar's own `doc:<uuid>` shape was recognised, so this answered
    /// `.unreadableInternal` — "Couldn't read what was dragged" — and filing a
    /// document from the library pane could not be done at all.
    func testLibraryPaneDragOntoASidebarFolderIsRecognisedAsAMove() {
        XCTAssertEqual(
            classifySidebarDropPayload(
                loadedIDs: [libraryDragJSON()],
                hasExternalPayload: true,
                carriesOwnProcessFlavor: true
            ),
            .internalItems(["doc:11111111-2222-3333-4444-555555555555"]),
            "a library-pane drag must move, not report itself unreadable"
        )
    }

    /// It must come back in the `doc:` shape, because every downstream consumer
    /// (`handleDropIntoFolder`, `handleLibraryHeaderItemDrop`,
    /// `handleExternalInsertionDrop`) filters on that prefix. Returning a bare
    /// id would be silently dropped by all three.
    func testLibraryDragIDIsReturnedInTheDocPrefixedShape() throws {
        let id = try XCTUnwrap(internalSidebarItemID(fromLibraryDragJSON: libraryDragJSON()))
        XCTAssertTrue(id.hasPrefix("doc:"))
        XCTAssertTrue(isInternalSidebarItemID(id), "the result must satisfy the sidebar's own id test")
    }

    /// Artifacts, notes and annotations are not documents and cannot be
    /// reparented — the same exclusion `moveDraggedItems` already makes. Letting
    /// them through would send a non-document id to the document move endpoint.
    func testNonDocumentLibraryKindsAreNotTreatedAsMovableItems() {
        for kind in ["artifact", "note", "annotation"] {
            XCTAssertNil(
                internalSidebarItemID(fromLibraryDragJSON: libraryDragJSON(kind: kind)),
                "\(kind) is not a document and must not be reparented"
            )
        }
    }

    /// A transcript that happens to start with a brace is not a payload, and a
    /// Finder path is not JSON. Neither may be mistaken for an internal drag —
    /// a false positive here would REFUSE a genuine external import.
    func testNonJSONAndMalformedJSONAreNotInternalDrags() {
        XCTAssertNil(internalSidebarItemID(fromLibraryDragJSON: "/Users/ann/Diary.pdf"))
        XCTAssertNil(internalSidebarItemID(fromLibraryDragJSON: "{ not really json"))
        XCTAssertNil(internalSidebarItemID(fromLibraryDragJSON: ""))
        XCTAssertNil(
            internalSidebarItemID(fromLibraryDragJSON: #"{"unrelated":"object"}"#),
            "a JSON object that is not a LibraryItemDrag must not decode into one"
        )
    }

    /// A genuine Finder drag must still import. If JSON recognition ever
    /// over-matched, external imports would start being refused instead — the
    /// opposite failure, equally silent.
    func testFinderDragIsUnaffectedByLibraryDragRecognition() {
        XCTAssertEqual(
            classifySidebarDropPayload(
                loadedIDs: ["/Users/ann/Scans/Diary.pdf"],
                hasExternalPayload: true,
                carriesOwnProcessFlavor: false
            ),
            .externalFiles
        )
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
        // 6c1519367 (#4474/#4475) lifted the classifier call INTO the shared
        // reader: the header no longer spells classifySidebarDropPayload
        // itself — it calls readSidebarDropPayload, the same entry the row
        // path and the folder cell use, and THAT is the one place allowed to
        // classify. The pin follows: header → shared reader → classifier.
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarSectionHeader.swift")
        XCTAssertTrue(source.contains("readSidebarDropPayload(providers)"))
        XCTAssertTrue(source.contains("sidebarDropMightCarryInternalID("))
        XCTAssertFalse(
            source.contains("classifySidebarDropPayload("),
            "classifying here again would be the second copy of the decision (#4401)"
        )
        let reader = try Self.appSource("Views/Sidebar/ItemRow/SidebarDropProviderReader.swift")
        XCTAssertTrue(
            reader.contains("classifySidebarDropPayload("),
            "the shared reader is the one caller of the pure classifier"
        )
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
