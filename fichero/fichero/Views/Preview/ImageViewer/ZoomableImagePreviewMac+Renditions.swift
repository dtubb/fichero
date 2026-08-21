#if os(macOS)
import SwiftUI

extension ZoomableImagePreview {
    /// Load this page's renditions (2026-08-20 bbox review).
    ///
    /// The list arrives in ENGINE order — primary first, then role preference,
    /// then a deterministic tiebreak — and is used as delivered. Re-sorting
    /// client-side would recreate exactly the disagreement about what "next"
    /// means that deciding the order server-side exists to prevent.
    ///
    /// Lives here so the (large) preview struct body stays under the
    /// type-body-length budget, same reason `loadOCRGeometry` moved out.
    func loadRenditions() async {
        renditions = []
        renditionIndex = 0
        guard let documentId, let renditionService else { return }
        // Only renditions whose bytes are expected to exist: a
        // referenced-but-absent staging entry is a knowable state in the
        // model, but it should never become a step in a flip sequence.
        await renditionService.load(documentId: documentId)
        renditions = renditionService.displayable(documentId: documentId)
    }

    /// What the toolbar shows about the current rendition.
    ///
    /// `nil` when there is nothing worth saying — no service, no document, or
    /// a page with a single rendition, where naming it would be noise. The
    /// toolbar hides the whole section in that case rather than greying it.
    var renditionNav: ReaderRenditionNav? {
        guard renditions.count > 1 else { return nil }
        let index = min(max(renditionIndex, 0), renditions.count - 1)
        let current = renditions[index]
        return ReaderRenditionNav(
            name: current.displayName,
            index: index,
            count: renditions.count,
            hasOwnFrame: current.hasOwnFrame,
            // Both actions nil until a rendition-bytes endpoint exists — see
            // ReaderRenditionNav.goPrevious for why this ships as an indicator
            // rather than a control. The presence of a closure IS the
            // capability; a separate canGo* flag would be a second way to say
            // the same thing, free to disagree with it.
            goPrevious: nil,
            goNext: nil
        )
    }
}
#endif
