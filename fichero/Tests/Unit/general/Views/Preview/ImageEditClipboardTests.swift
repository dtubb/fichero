@testable import Fichero
import Foundation
import Testing

/// Copy Edits / Paste Edits — Lightroom's Copy & Paste Settings, carried on the
/// non-destructive RECIPE rather than the pixels (Daniel, 2026-09-02: "copy the
/// edits on one image and paste them on others").
struct ImageEditClipboardTests {
    private func source(_ relative: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private func modelSource() throws -> String {
        try source("Views/Preview/ImageEditor/ImageEditorModel.swift")
    }

    @MainActor
    @Test("copied steps drop the per-document bookkeeping before they travel")
    func clipboardSanitisesBeforeTravel() throws {
        let copied = ImageEditClipboard.sanitized([
            AnyCodable([
                "op": "rotate",
                "page": 1,
                "params": ["angle": 90],
                "derived_path": "/tmp/fichero-image-edits/doc-a/page-1/latest.png",
                "created_at": "2026-09-02T00:00:00Z"
            ] as [String: Any])
        ])
        let dict = try #require(copied.first?.value as? [String: Any])
        // The recipe survives…
        #expect(dict["op"] as? String == "rotate")
        #expect((dict["params"] as? [String: Any])?["angle"] as? Int == 90)
        // …the pointer at another document's cached pixels does not.
        #expect(dict["derived_path"] == nil)
        #expect(dict["created_at"] == nil)
    }

    @Test("paste replaces the target chain rather than appending to it")
    func pasteReplacesRatherThanAppends() throws {
        let model = try modelSource()
        #expect(model.contains("func pasteEdits() async"))
        #expect(model.contains("func pasteEdits(to documentIds: [String]) async"))
        // setOperations REPLACES the chain — pasting the same copy twice must
        // not rotate the image twice.
        #expect(model.contains("operations: ImageEditClipboard.sanitized(operations)"))
        #expect(model.contains("try await service.setOperations(documentId: id, operations: operations)"))
        // The many-document form reuses the collected-failures batch runner.
        #expect(model.contains("await batchApply(documentIds: documentIds)"))
    }

    @Test("pasting across a selection asks first; pasting onto one image does not")
    func pasteAcrossSelectionConfirms() throws {
        let clipboard = try source("Views/Preview/ImageEditor/ImageEditorView+Clipboard.swift")
        #expect(clipboard.contains("accessibilityIdentifier(\"imageEditCopyEdits\")"))
        #expect(clipboard.contains("accessibilityIdentifier(\"imageEditPasteEdits\")"))
        #expect(clipboard.contains("accessibilityIdentifier(\"imageEditPasteEditsToSelection\")"))
        #expect(clipboard.contains("isPresented: $showPasteManyConfirm"))
        // Paste-to-many only appears when there IS a multi-selection.
        #expect(clipboard.contains("if selectedEditableDocs.count > 1 {"))
        // The single-image paste runs straight off the menu, unguarded.
        #expect(clipboard.contains("Task { await model.pasteEdits() }"))
    }

    @MainActor
    @Test("copying an empty chain is a real copy, not a no-op")
    func copyingAnEmptyChainReplacesTheClipboard() {
        let clipboard = ImageEditClipboard.shared
        defer { clipboard.clear() }

        clipboard.copy(
            operations: [AnyCodable(["op": "rotate", "page": 1] as [String: Any])],
            fromDocumentId: "doc-a"
        )
        #expect(clipboard.count == 1)
        #expect(clipboard.sourceDocumentId == "doc-a")

        // "This image has no edits" is a state worth pasting. Refusing to
        // record it would leave the previous copy in place and paste the
        // WRONG recipe on the next Paste.
        clipboard.copy(operations: [], fromDocumentId: "doc-b")
        #expect(clipboard.isEmpty)
        #expect(clipboard.sourceDocumentId == "doc-b")

        clipboard.clear()
        #expect(clipboard.isEmpty)
        #expect(clipboard.sourceDocumentId == nil)
    }
}
