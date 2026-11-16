import FicheroAPIClient
import SwiftUI

extension ReadingPaneView {
    /// The head's try controls (the try label, Accept all N): moved out of `ReadingPaneView` to keep that file from growing.
    @ViewBuilder
    var readerHeadTryControls: some View {
        if let documentId = effectiveDocument?.id {
            TryLabelButton(pageId: documentId)
            ReviewAcceptAllButton(documentId: documentId)
        }
    }
}
