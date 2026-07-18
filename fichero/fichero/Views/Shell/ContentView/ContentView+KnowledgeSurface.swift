import SwiftUI

extension ContentView {
    @ViewBuilder
    func knowledgeSurface(
        for document: Document?,
        activePageNumber: Int?,
        pageCount: Int?,
        scrollSync: DocumentScrollSyncState,
        onPageSelected: @escaping (Int) -> Void
    ) -> some View {
        if let document, let libraryPath = apiClient.currentLibraryPath, !libraryPath.isEmpty {
            // For page documents (PDF pages), use the PARENT's doc ID so the
            // WebKit view doesn't reload (and reset scroll) when the user pages
            // through a PDF. activePageNumber drives in-page scroll via JS. (#1346)
            let kgDocumentId = (document.docType == .page && document.parentId != nil)
                ? document.parentId!
                : document.id
            DocumentKGSurface(
                documentId: kgDocumentId,
                documentScope: document.docType == .page ? .page : .folder,
                libraryPath: libraryPath,
                selectedEntityId: kgFocusState.focusedEntityId,
                selectedClaimId: kgFocusState.focusedClaimId ?? claimFocusState.selectedClaimId,
                activePageNumber: activePageNumber,
                pageCount: pageCount,
                onPageSelected: onPageSelected,
                scrollSync: scrollSync
            )
        } else {
            Text("No selection")
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(.textBackgroundColor))
        }
    }
}
