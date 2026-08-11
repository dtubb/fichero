import XCTest

@testable import Fichero

/// #4401's surviving instance: the two WIDEST drop targets in the app imported
/// an internal drag.
///
/// The row-level paths were fixed three times — the sidebar row, the library
/// header, the library folder cell — and each fix covered drops that land ON a
/// row. Two targets sit above all of them and were never screened:
///
///   1. `DropTargetModifiers` mounts `.dropDestination(for: URL.self)` on the
///      WHOLE `NavigationSplitView` (its own comment says so: "sidebar column
///      AND detail column both"). Since #4123 a document row exports a real file
///      via `FileRepresentation`, so this destination resolves an internal drag
///      to that file and hands it to `handleFileDrop` → `importFiles`.
///   2. `detailColumn` mounts `.onDrop(of: [.item])`. `.item` is UTType's root,
///      so it matches every in-app drag, and the shared loader then resolves the
///      same exported file.
///
/// Both produced the reported symptom exactly: a second document appears, and it
/// is hollow because it is a fresh import that has never been processed. It also
/// explains why the symptom outlived the row fixes — releasing a drag over
/// sidebar whitespace, a section gap, or the content pane never reaches a row.
///
/// The rule under test is #4401's: **a drop must never silently re-import an
/// item that is already in the library.**
final class ContentPaneInternalDragImportGuardTests: XCTestCase {

    // MARK: - The predicate, behaviourally

    private func exportedDragURL(named name: String = "Diary.pdf") -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("\(ficheroInternalDragExportPrefix)\(UUID().uuidString)",
                                    isDirectory: true)
            .appendingPathComponent(name)
    }

    /// The exact URL shape `SidebarDragID.exportSourceFile` produces. If this
    /// stops matching, every guard below silently stops guarding.
    func testTheAppsOwnDragExportIsRecognised() {
        XCTAssertTrue(isFicheroInternalDragExport(exportedDragURL()))
    }

    /// A genuine Finder drag must still import. A guard that refuses everything
    /// trades one data bug for a dead feature.
    func testAFinderURLIsNotAnInternalExport() {
        XCTAssertFalse(
            isFicheroInternalDragExport(URL(fileURLWithPath: "/Users/ann/Documents/Diary.pdf"))
        )
    }

    /// `fichero-drop-` stages INBOUND external bytes and `fichero-drag-` stages
    /// our OUTBOUND export. One character apart, opposite meanings: confusing
    /// them would refuse every real drop the sidebar stages for copy-ingest.
    func testTheInboundDropStagingDirectoryIsNotMistakenForAnExport() {
        let staged = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-drop-\(UUID().uuidString)", isDirectory: true)
            .appendingPathComponent("FromFinder.pdf")
        XCTAssertFalse(
            isFicheroInternalDragExport(staged),
            "fichero-drop- is an inbound external drop; refusing it breaks Finder imports"
        )
    }

    /// The marker is a path COMPONENT, not a substring — a user folder merely
    /// named `my-fichero-drag-notes` is not our export.
    func testTheMarkerMustBeAWholePathComponent() {
        let user = URL(fileURLWithPath: "/Users/ann/my-fichero-drag-notes/Diary.pdf")
        XCTAssertFalse(isFicheroInternalDragExport(user))
    }

    // MARK: - The partition

    /// A mixed drop must not be all-or-nothing in either direction: the real
    /// files still import and the internal one still does not.
    func testAMixedDropImportsOnlyTheGenuinelyExternalFiles() {
        let finder = URL(fileURLWithPath: "/Users/ann/Scans/Page1.tiff")
        let ours = exportedDragURL()

        let (external, internalExports) = partitionFicheroInternalDragExports([finder, ours])

        XCTAssertEqual(external, [finder])
        XCTAssertEqual(internalExports, [ours])
    }

    /// The everyday case: nothing to refuse, nothing withheld.
    func testAPurelyExternalDropIsUntouched() {
        let urls = [
            URL(fileURLWithPath: "/Users/ann/A.pdf"),
            URL(fileURLWithPath: "/Users/ann/B.pdf")
        ]
        let (external, internalExports) = partitionFicheroInternalDragExports(urls)

        XCTAssertEqual(external, urls, "a Finder drag must import exactly as before")
        XCTAssertTrue(internalExports.isEmpty)
    }

    /// The reported bug, stated as the assertion that would have caught it:
    /// dragging a document out of the sidebar and releasing it over the window
    /// yields NOTHING to import.
    func testASidebarDragReleasedOverTheWindowImportsNothing() {
        let (external, internalExports) = partitionFicheroInternalDragExports([exportedDragURL()])

        XCTAssertTrue(
            external.isEmpty,
            "importing this is #4401: a second, hollow copy of a document already in the library"
        )
        XCTAssertEqual(internalExports.count, 1, "and the refusal must be reportable, not silent")
    }

    // MARK: - Both call sites actually apply it

    private static func importSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Shell
            .deletingLastPathComponent()   // Views
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero")
            .appendingPathComponent("Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "the import actions file is empty — these guards measure nothing")
        return source
    }

    private static func handleFileDropBody() throws -> String {
        try importSource()
            .components(separatedBy: "func handleFileDrop(urls: [URL]) {")[1]
    }

    /// A pure predicate nothing calls protects nothing — #4408's "wired but
    /// unfed" shape, which is how the preceding bridge shipped green.
    func testTheURLTypedRouteScreensBeforeClassifying() throws {
        let source = try Self.importSource()
        XCTAssertTrue(
            source.contains("partitionFicheroInternalDragExports(urls)"),
            "the screening helper must actually call the partition"
        )
        let body = try Self.handleFileDropBody()
        let guardIndex = try XCTUnwrap(body.range(of: "externalURLsRefusingOwnDragExports(urls)"))
        let classifyIndex = try XCTUnwrap(body.range(of: "DroppedURLs.classify"))
        XCTAssertTrue(
            guardIndex.lowerBound < classifyIndex.lowerBound,
            "the screen must run BEFORE the URLs reach the import classifier"
        )
    }

    /// ...and the surviving external set is what gets imported, not the
    /// original list — screening that classifies the unfiltered array is a
    /// no-op that reads like a fix.
    func testTheImportUsesTheScreenedURLsNotTheOriginalList() throws {
        let body = try Self.handleFileDropBody()
        XCTAssertTrue(body.contains("DroppedURLs.classify(external)"))
        XCTAssertFalse(
            body.contains("DroppedURLs.classify(urls)"),
            "classifying the unscreened list re-imports the internal drag anyway"
        )
    }

    /// The provider-typed route identifies the drag POSITIVELY, by the id it
    /// carries — the primary #4401 defence — and must do so before it resolves
    /// any file URL, because resolving one is what triggers the import.
    func testTheProviderRouteReadsThePayloadBeforeLoadingAnyURL() throws {
        let body = try Self.importSource()
            .components(separatedBy: "func handleContentPaneExternalDrop(")[1]
            .components(separatedBy: "\n    func handleFileDrop")[0]
        let readIndex = try XCTUnwrap(body.range(of: "readSidebarDropPayload(providers"))
        let loadIndex = try XCTUnwrap(body.range(of: "ExternalFileDropLoader.loadAnyFileURL"))
        XCTAssertTrue(
            readIndex.lowerBound < loadIndex.lowerBound,
            "reading the payload after resolving a URL is the #4123-caused ordering bug again"
        )
        XCTAssertTrue(
            body.contains("case .internalItems, .unreadableInternal:"),
            "an in-app drag whose id could not be read must be refused, never imported"
        )
    }

    /// A refusal the user cannot see is indistinguishable from the item
    /// vanishing — the OS was already told the drop was accepted.
    func testBothRoutesReportTheRefusal() throws {
        // Rewritten twice, each by a ruling:
        // #4311 killed "already in this library" (claimed knowledge the path
        // cannot have); then Daniel #133 (2026-08-09, 799d2f62c) killed the
        // ALERT itself — a no-op internal drop logs and snaps back, it never
        // panels. The pin now follows THAT ruling: both routes refuse
        // LOUDLY IN THE LOG, and neither shows alert text.
        let source = try Self.importSource()
        XCTAssertEqual(
            source.components(
                separatedBy: "refusing to import (no-op, no alert)"
            ).count - 1, 1,
            "the provider route must log its internal-drop refusal"
        )
        XCTAssertEqual(
            source.components(
                separatedBy: "dragged from inside the app (no-op, no alert)"
            ).count - 1, 1,
            "the URL route must log its internal-export refusal"
        )
        XCTAssertFalse(
            source.contains("That item was dragged from inside Fichero, so it wasn't imported."),
            "the alert wording is back — Daniel #133: no-op drops never panel"
        )
        XCTAssertFalse(
            source.contains("That item is already in this library."),
            "the refusal must not claim a library it cannot know (#4311)"
        )
    }
}
