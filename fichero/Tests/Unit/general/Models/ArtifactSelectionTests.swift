@testable import Fichero
import Foundation
import Testing

// Tests for the artifacts-browser multi-select + delete helpers (#2519).
// Covers: delete resolves the FULL selection (not just the focused row),
// stale/empty ids are dropped, and detail-follow focus rules across
// empty / single / multi selection — the behaviours that drive the List.

@Suite("ArtifactSelection — multi-select + delete helpers (#2519)")
struct ArtifactSelectionTests {

    private func artifact(_ id: String, documentId: String = "doc-1") -> Artifact {
        Artifact(id: id, documentId: documentId, sourceArtifactId: nil,
                 version: 1, artifactType: "transcript", content: nil,
                 data: nil, runId: nil, provider: nil, model: nil,
                 stepName: "transcript", confidence: nil,
                 reviewed: false, createdAt: Date())
    }

    private var items: [Artifact] {
        [artifact("a"), artifact("b"), artifact("c")]
    }

    private func document(
        _ id: String,
        parentId: String? = nil,
        docType: DocType = .file,
        name: String,
        sequence: Int? = nil
    ) -> Document {
        Document(
            id: id,
            parentId: parentId,
            docType: docType,
            fileType: docType == .file ? .pdf : nil,
            name: name,
            sequence: sequence,
            status: .completed
        )
    }

    // MARK: - resolve (delete acts on the full selection)

    @Test("resolve returns every selected artifact, in list order")
    func resolveFullSelection() {
        let result = ArtifactSelection.resolve(["c", "a"], in: items)
        #expect(result.map(\.id) == ["a", "c"])  // list order, not set order
    }

    @Test("resolve on an empty selection is empty (regression: no delete-all)")
    func resolveEmpty() {
        #expect(ArtifactSelection.resolve([], in: items).isEmpty)
    }

    @Test("resolve drops ids not present in items (stale / already-deleted)")
    func resolveDropsStale() {
        let result = ArtifactSelection.resolve(["a", "ghost"], in: items)
        #expect(result.map(\.id) == ["a"])
    }

    @Test("resolve against an empty list is empty")
    func resolveEmptyList() {
        #expect(ArtifactSelection.resolve(["a"], in: []).isEmpty)
    }

    // MARK: - focusedID (detail follows a single selection)

    @Test("empty selection clears focus")
    func focusEmpty() {
        #expect(ArtifactSelection.focusedID(for: [], current: "a") == nil)
    }

    @Test("single selection focuses that row")
    func focusSingle() {
        #expect(ArtifactSelection.focusedID(for: ["b"], current: "a") == "b")
    }

    @Test("multi-selection keeps the current focus (no jump during batch delete)")
    func focusMultiKeepsCurrent() {
        #expect(ArtifactSelection.focusedID(for: ["a", "b"], current: "a") == "a")
        // current may be nil while multi-selecting — stays nil, doesn't pick arbitrarily
        #expect(ArtifactSelection.focusedID(for: ["a", "b"], current: nil) == nil)
    }

    @MainActor
    @Test("FocusedArtifact keeps document scope with the selected artifact")
    func focusedArtifactTracksDocumentScope() {
        let focused = FocusedArtifact()
        let artifact = artifact("artifact-1", documentId: "doc-42")

        focused.select(
            artifact.id,
            documentId: "doc-42",
            documentName: "Document 42",
            in: [artifact]
        )

        #expect(focused.id == "artifact-1")
        #expect(focused.documentId == "doc-42")
        #expect(focused.documentName == "Document 42")
        #expect(focused.artifact?.id == "artifact-1")
    }

    @Test("artifacts pane preserves selection when routing within the same document")
    func artifactsPanePreservesSameDocumentSelection() {
        #expect(
            ArtifactInspectorFocusRouting.shouldClearSelection(
                focusedDocumentId: "doc-42",
                inspectedDocumentId: "doc-42"
            ) == false
        )
    }

    @Test("artifacts pane clears selection when switching documents")
    func artifactsPaneClearsCrossDocumentSelection() {
        #expect(
            ArtifactInspectorFocusRouting.shouldClearSelection(
                focusedDocumentId: "doc-42",
                inspectedDocumentId: "doc-99"
            )
        )
        #expect(
            ArtifactInspectorFocusRouting.shouldClearSelection(
                focusedDocumentId: nil,
                inspectedDocumentId: "doc-99"
            ) == false
        )
    }

    @Test("artifact provenance marks descendant page outputs with page labels")
    func artifactProvenanceDescendantPage() {
        let pdf = document("doc-parent", name: "Notebook.pdf")
        let page = document("page-3", parentId: pdf.id, docType: .page, name: "page_0003", sequence: 3)
        let artifact = artifact("artifact-1", documentId: page.id)

        let display = ArtifactProvenance.display(
            for: artifact,
            inspectedDocument: pdf,
            documentsById: [pdf.id: pdf, page.id: page]
        )

        #expect(display.sourceLabel == "Page 3")
        #expect(display.pageLabel == "3")
        #expect(display.relation == .descendantPage)
    }

    @Test("artifact provenance marks same-document outputs as local")
    func artifactProvenanceCurrentDocument() {
        let pdf = document("doc-parent", name: "Notebook.pdf")
        let artifact = artifact("artifact-1", documentId: pdf.id)

        let display = ArtifactProvenance.display(
            for: artifact,
            inspectedDocument: pdf,
            documentsById: [pdf.id: pdf]
        )

        #expect(display.sourceLabel == "This document")
        #expect(display.relation == .currentDocument)
    }

    @Test("artifact provenance row subtitle joins source workflow and provider")
    func artifactProvenanceRowSubtitle() {
        let pdf = document("doc-parent", name: "Notebook.pdf")
        let artifact = Artifact(
            id: "artifact-1",
            documentId: pdf.id,
            sourceArtifactId: nil,
            version: 1,
            artifactType: "transcription",
            content: nil,
            data: nil,
            runId: nil,
            provider: "OpenAI",
            model: "gpt-4.1",
            stepName: "OCR",
            confidence: nil,
            reviewed: false,
            createdAt: Date()
        )

        let display = ArtifactProvenance.display(
            for: artifact,
            inspectedDocument: pdf,
            documentsById: [pdf.id: pdf]
        )

        #expect(display.rowSubtitle == "This document · OCR · OpenAI · gpt-4.1")
    }
}
