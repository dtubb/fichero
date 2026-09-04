// Original ↔ edited is the up/down flip (Daniel, 2026-09-03: "these should be
// a rendition so we can easily go back and forth"). The two states are not
// rows — an edit chain is a recipe the engine renders on demand — so their
// ids say which state they are and the service renders them through the
// image-preview endpoint instead of the rendition-bytes route.

@testable import Fichero
import Foundation
import Testing

struct RenditionEditStatesTests {
    private func staged(_ role: String) -> DocumentRendition {
        DocumentRendition(
            id: "row-\(role)", documentId: "doc-1", role: role, path: "/\(role).jpg",
            isPrimary: role == "original", pixelWidth: nil, pixelHeight: nil,
            isMaterialized: true, hasOwnFrame: false, note: nil
        )
    }

    @Test("a document with no edits gains no states — a one-entry flip strip is noise")
    func noChainNoStates() {
        #expect(
            DocumentRendition.editStates(documentId: "doc-1", operationKinds: [], existingCount: 0)
                .isEmpty
        )
    }

    @Test("an edited plain image gets BOTH states, so the flip has somewhere to go")
    func plainImageGetsOriginalAndEdited() {
        let states = DocumentRendition.editStates(
            documentId: "doc-1", operationKinds: ["enhance"], existingCount: 0
        )
        #expect(states.map(\.role) == [DocumentRendition.originalRole, DocumentRendition.editedRole])
        #expect(states.allSatisfy(\.isMaterialized))
        #expect(states.allSatisfy(\.isEditState))
    }

    @Test("a page that already has staged renditions gains only the edited state")
    func stagedPagesGetOnlyEdited() {
        // Index 0 of the engine's list is already the untouched pixels; a
        // second "Original" would be the same image twice in the sequence.
        let states = DocumentRendition.editStates(
            documentId: "doc-1", operationKinds: ["rotate"], existingCount: 2
        )
        #expect(states.map(\.role) == [DocumentRendition.editedRole])
    }

    @Test("only a step that moves pixels gives the edited state its own frame")
    func frameHonesty() {
        func edited(_ ops: [String]) -> DocumentRendition {
            DocumentRendition.editStates(
                documentId: "doc-1", operationKinds: ops, existingCount: 1
            )[0]
        }
        // An enhance leaves every OCR box exactly where it was — overlays keep drawing.
        #expect(!edited(["enhance"]).hasOwnFrame)
        #expect(!edited(["enhance", "remove_background"]).hasOwnFrame)
        // A crop/rotate/straighten re-frames the render — node-frame boxes must skip it.
        #expect(edited(["crop"]).hasOwnFrame)
        #expect(edited(["enhance", "rotate"]).hasOwnFrame)
        #expect(edited(["straighten"]).hasOwnFrame)
    }

    @Test("edit-state ids name their state and their document")
    func idsAreDocumentScoped() {
        let mine = DocumentRendition.editStateId(role: "edited", documentId: "doc-1")
        let yours = DocumentRendition.editStateId(role: "edited", documentId: "doc-2")
        // The content cache is keyed by rendition id alone: a shared sentinel
        // would serve one document's edited pixels for another's.
        #expect(mine != yours)
        #expect(DocumentRendition.editStateRole(of: mine) == "edited")
        #expect(DocumentRendition.editStateRole(of: yours) == "edited")
        #expect(
            DocumentRendition.editStateRole(
                of: DocumentRendition.editStateId(role: "original", documentId: "doc-1")
            ) == "original"
        )
    }

    @Test("a real rendition row is never mistaken for an edit state")
    func realRowsAreNotEditStates() {
        #expect(DocumentRendition.editStateRole(of: "row-enhanced") == nil)
        #expect(DocumentRendition.editStateRole(of: UUID().uuidString) == nil)
        #expect(!staged("enhanced").isEditState)
        // A degenerate id is not silently treated as a state either.
        #expect(DocumentRendition.editStateRole(of: "edit:") == nil)
    }
}
