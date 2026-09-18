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
        let allMaterialized = states.allSatisfy { $0.isMaterialized }
        let allEditStates = states.allSatisfy { $0.isEditState }
        #expect(allMaterialized)
        #expect(allEditStates)
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
        // Flips and auto-crop ALSO move pixels (CD 2026-09-16: "highlights/boxes/readings end up
        // in the wrong spot"). They were MISSING from `frameChangingOps`, so an edited page built
        // only from them computed hasOwnFrame:false → the overlay frame-gate opened → all three
        // overlays drew over mirrored/cropped pixels. A flip mirrors x→1−x−w, so edge words are
        // maximally wrong while centred ones look fine. These pin the engine's full reframing set.
        #expect(edited(["flip_horizontal"]).hasOwnFrame)
        #expect(edited(["flip_vertical"]).hasOwnFrame)
        #expect(edited(["auto_crop_border"]).hasOwnFrame)
        #expect(edited(["enhance", "flip_horizontal"]).hasOwnFrame)
    }

    @Test("frameChangingOps mirrors the engine's pixel-moving ops (a missing one misplaces overlays)")
    func frameChangingOpsCoversEngineReframingSet() {
        // The client list MUST include every engine op that re-frames the image. Each entry below
        // names where the engine defines/dispatches it, so a coverage test can't itself go stale by
        // hand-typing an expectation that silently drops an op (that is exactly how auto_deskew went
        // missing: this list didn't know about media/image_ops.py:253's rotate-dispatch branch).
        // If the engine adds a reframing op, add it BOTH here and to `frameChangingOps`, or overlays
        // silently misplace on pages edited with it — the exact 2026-09-16 regression.
        let reframing = [
            "crop", "auto_crop_border", // media/image_ops.py:274,285
            "rotate", "straighten", // media/image_ops.py:253 dispatch branch
            "flip_horizontal", "flip_vertical", // media/image_ops.py:288-290
            "auto_deskew" // media/image_ops.py:253 dispatch branch; produced by workflows/tools/deskew_images.py
        ]
        for op in reframing {
            #expect(DocumentRendition.frameChangingOps.contains(op), "\(op) re-frames but isn't gated")
        }
        #expect(
            DocumentRendition.frameChangingOps == Set(reframing),
            "frameChangingOps has an op not in this fixture (or vice versa) — update both together"
        )
        // Same-frame ops (media/image_ops.py dispatch: sharpen:296, enhance:300, grayscale:323,
        // denoise:309, remove_background:319, adaptive_binarize:311). "threshold" and
        // "background_clean" are PARAMS of remove_background/fuzzy_clean, not op kinds — there is no
        // such op name to assert against.
        for safe in ["enhance", "grayscale", "denoise", "remove_background", "adaptive_binarize", "sharpen"] {
            #expect(!DocumentRendition.frameChangingOps.contains(safe), "\(safe) keeps the frame — don't gate it")
        }
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
