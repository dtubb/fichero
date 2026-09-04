@testable import Fichero
import XCTest

/// Export what you are READING (Daniel, 2026-09-03: "for export, we want a way
/// to easily export to Word or MD file — say, from the reader view").
///
/// Two guarantees this pins:
///  1. The commands are enabled by a value only the READER publishes, so they
///     never tease outside a reader — the `readerLens` / `readerZoomActions`
///     contract, applied to a verb that writes files.
///  2. Neither format grows a second implementation: Markdown is the bytes
///     `ReaderMarkdownDrag` already promises, Word is the engine's existing
///     `/api/export/word` service reached through the generated client.
final class ReaderExportFocusedValueTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }

    private func target(_ id: String, _ name: String, _ text: String) -> ReaderExportTargets.Item {
        ReaderExportTargets.Item(id: id, name: name, text: text)
    }

    // MARK: - What the commands act on

    func testSingleSelectionExportsTheOneDocument() {
        let targets = ReaderExportTargets(items: [target("d1", "Diary 1933", "Enero primero")])
        XCTAssertEqual(targets.items.map(\.id), ["d1"])
        XCTAssertEqual(targets.suggestedStem, "Diary 1933")
        XCTAssertFalse(targets.isEmpty)
    }

    /// Visible-surface selection ruling: the verb acts on what you can SEE, so
    /// a multi-document reader exports every document it renders — and names
    /// the count, because a save panel cannot name three files.
    func testMultiSelectionExportsEveryVisibleDocument() {
        let targets = ReaderExportTargets(items: [
            target("d1", "Page 1", "uno"),
            target("d2", "Page 2", "dos"),
            target("d3", "Page 3", "tres")
        ])
        XCTAssertEqual(targets.items.count, 3)
        XCTAssertEqual(targets.suggestedStem, "3 Documents")
    }

    func testNoReaderMeansNothingToExport() {
        XCTAssertTrue(ReaderExportTargets(items: []).isEmpty)
        XCTAssertTrue(ReaderExportTargets(items: []).markdownItems.isEmpty)
    }

    // MARK: - Markdown has nothing to promise for an unread page

    func testUnreadPagesAreNotMarkdownExportable() {
        let targets = ReaderExportTargets(items: [
            target("d1", "Unread", ""),
            target("d2", "Whitespace", "   \n  "),
            target("d3", "Read", "hay texto")
        ])
        // Same refusal `ReaderMarkdownDrag.itemProvider` makes for empty text:
        // a command that would write an empty file should be disabled, not
        // silently succeed.
        XCTAssertEqual(targets.markdownItems.map(\.id), ["d3"])
        // Word stays available: the .docx is rendered by the engine from
        // everything it holds for the document, not from this text.
        XCTAssertFalse(targets.isEmpty)
    }

    // MARK: - Equatable, or the per-frame republish storm returns

    func testEqualAcrossBodyPassesWithTheSameDocuments() {
        // Two instances minted on different body passes must compare EQUAL, or
        // the focus system republishes every frame — the
        // "FocusedValue update tried to update multiple times per frame" fault
        // `SidebarActions` and `ImageZoomActions` both document.
        let first = ReaderExportTargets(items: [target("d1", "Diary", "texto")])
        let second = ReaderExportTargets(items: [target("d1", "Diary", "texto")])
        XCTAssertEqual(first, second)
    }

    func testNotEqualWhenTheSelectionChanges() {
        let one = ReaderExportTargets(items: [target("d1", "Diary", "texto")])
        let two = ReaderExportTargets(items: [target("d2", "Other", "texto")])
        XCTAssertNotEqual(one, two)
    }

    /// A page that finishes transcribing mid-session flips Markdown from
    /// disabled to enabled; the value must republish or the menu item stays
    /// dead over content that now exists.
    func testNotEqualWhenMarkdownAvailabilityChanges() {
        let before = ReaderExportTargets(items: [target("d1", "Diary", "")])
        let after = ReaderExportTargets(items: [target("d1", "Diary", "texto")])
        XCTAssertNotEqual(before, after)
    }

    // MARK: - Filenames

    func testWordFilenameSanitisesPathSeparators() {
        // "1933/34" must not promise a file inside a directory that does not
        // exist — the rule `ReaderMarkdownDrag.filename` already states.
        XCTAssertEqual(
            ReaderExportRunner.filename(forDocumentNamed: "1933/34", extension: "docx"),
            "1933-34.docx"
        )
        XCTAssertEqual(
            ReaderExportRunner.filename(forDocumentNamed: "", extension: "docx"),
            "Document.docx"
        )
        // A document already named like a Markdown file must not become
        // "notes.md.docx".
        XCTAssertEqual(
            ReaderExportRunner.filename(forDocumentNamed: "notes.md", extension: "docx"),
            "notes.docx"
        )
    }

    func testMarkdownFilenameComesFromTheDragRule() {
        XCTAssertEqual(ReaderMarkdownDrag.filename(forDocumentNamed: "Diary 1933"), "Diary 1933.md")
    }

    // MARK: - Source surface

    func testReaderPublishesItsExportTargets() throws {
        let source = try Self.appSource("Views/Reader/Page/ReadingPaneView.swift")
        XCTAssertTrue(source.contains(".focusedSceneValue(\\.readerExportTargets, readerExportTargets)"))
        // The pane's own context menu carries the same two commands, so the
        // verb is reachable where the reading is (Daniel: "from the reader view").
        XCTAssertTrue(source.contains("ReaderExportMenuItems()"))
    }

    func testFileMenuHostsTheSameCommands() throws {
        let source = try Self.appSource("App/Menus/FileMenuCommands.swift")
        XCTAssertTrue(source.contains("ReaderExportMenuItems()"))
    }

    func testCommandsDisableWithoutAFocusedReader() throws {
        let source = try Self.appSource("App/Menus/ReaderExportCommands.swift")
        XCTAssertTrue(source.contains("@FocusedValue(\\.readerExportTargets)"))
        XCTAssertTrue(source.contains(".disabled(targets?.markdownItems.isEmpty != false)"))
        XCTAssertTrue(source.contains(".disabled(currentLibrary == nil || targets?.isEmpty != false)"))
    }

    /// No second export implementation, and no hand-rolled networking: Word
    /// goes through the generated, tokened client's service wrapper.
    func testWordExportRoutesThroughTheExistingService() throws {
        let runner = try Self.appSource("App/Menus/ReaderExportRunner.swift")
        XCTAssertTrue(runner.contains("library.documentService.exportWord("))
        XCTAssertFalse(runner.contains("URLSession"))
        XCTAssertFalse(runner.contains("URLRequest"))

        let service = try Self.appSource("Services/DocumentService.swift")
        XCTAssertTrue(service.contains("client.api.exportWordRouteApiExportWordPost("))
    }

    /// The save panel already asked about replacing; a 409 from the engine
    /// would ask the same question again and lose the answer.
    func testSavePanelAnswerIsCarriedToTheEngine() throws {
        let runner = try Self.appSource("App/Menus/ReaderExportRunner.swift")
        XCTAssertTrue(runner.contains("overwrite: true"))
    }

    /// Word exports from the reader carry the reading content, not the
    /// library's knowledge-graph appendix — the default the service wrapper
    /// picks for this caller.
    func testWordWrapperDefaultsToNoKnowledgeGraphAppendix() throws {
        let service = try Self.appSource("Services/DocumentService.swift")
        XCTAssertTrue(service.contains("includeKnowledgeGraph: Bool = false"))
    }

    /// Every export presents the SAME panels and the same failure alert —
    /// a second copy of those five lines is how two exports start behaving
    /// differently.
    func testExportPanelsAreShared() throws {
        let legacy = try Self.appSource("App/Menus/FileMenuCommands+Export.swift")
        XCTAssertTrue(legacy.contains("ExportPresentation.savePanel("))
        XCTAssertTrue(legacy.contains("ExportPresentation.directoryPanel("))
        XCTAssertTrue(legacy.contains("ExportPresentation.showError("))
        XCTAssertFalse(legacy.contains("let savePanel = NSSavePanel()"))
    }
}
