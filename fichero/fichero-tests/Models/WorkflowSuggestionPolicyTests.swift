@testable import Fichero
import Testing

/// The contextual toolbar nudges (Daniel, 2026-08-25: "select a folder and
/// you can catalogue"): pure facts already in the selection, at most two
/// suggestions, silence for mixed bags — the ⚡ picker carries those.
struct WorkflowSuggestionPolicyTests {
    private func doc(_ id: String, docType: DocType = .file,
                     fileType: FileType? = nil, nodeKind: String = "document") -> Document {
        Document(id: id, docType: docType, fileType: fileType, name: id, nodeKind: nodeKind)
    }

    @Test("a folder selection offers Catalogue first")
    func folderOffersCatalogue() {
        let suggestions = WorkflowSuggestionPolicy.suggestions(
            for: [doc("f1", docType: .folder), doc("f2", docType: .folder)]
        )
        #expect(suggestions.first?.workflowName == "Catalogue")
        #expect(suggestions.count == 2)
    }

    @Test("images offer transcription and regions")
    func imagesOfferReading() {
        let suggestions = WorkflowSuggestionPolicy.suggestions(
            for: [doc("i1", fileType: .image)]
        )
        #expect(suggestions.map(\.workflowName)
            == ["Transcribe (Auto-Detect)", "Detect Regions"])
    }

    @Test("entries offer entities then claims")
    func entriesOfferStructure() {
        let suggestions = WorkflowSuggestionPolicy.suggestions(
            for: [doc("e1", nodeKind: "entry"), doc("e2", nodeKind: "entry")]
        )
        #expect(suggestions.first?.workflowName == "Extract Entities")
    }

    @Test("a mixed selection and an empty one stay silent")
    func mixedAndEmptyAreSilent() {
        #expect(WorkflowSuggestionPolicy.suggestions(for: []).isEmpty)
        #expect(WorkflowSuggestionPolicy.suggestions(
            for: [doc("f", docType: .folder), doc("i", fileType: .image)]
        ).isEmpty)
    }
}
