import SwiftUI

// MARK: - Source Highlight

extension PageContentPane {

    func updateSourceHighlight(_ note: Notification) {
        guard let doc = pageDoc,
              let info = note.userInfo,
              let highlight = PageContentClaimSourceHighlight.match(
                content: pageContent,
                documentId: doc.id,
                info: info
              ) else { return }
        sourceHighlight = highlight
        sourceHighlightToken = UUID()
    }

    func syncSourceHighlightFromClaimFocus() {
        guard let doc = pageDoc else {
            sourceHighlight = nil
            return
        }
        let info: [AnyHashable: Any] = [
            "documentId": claimFocusState.selectedClaimSourceDocumentId as Any,
            "claimText": claimFocusState.selectedClaimText as Any,
            "charStart": claimFocusState.selectedClaimCharStart as Any,
            "charEnd": claimFocusState.selectedClaimCharEnd as Any
        ]
        guard let highlight = PageContentClaimSourceHighlight.match(
            content: pageContent,
            documentId: doc.id,
            info: info
        ) else {
            sourceHighlight = nil
            return
        }
        sourceHighlight = highlight
        sourceHighlightToken = UUID()
    }
}
