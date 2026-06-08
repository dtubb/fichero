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
                documentScopeLabel: document.docType == .page ? "This page only" : "This folder only",
                libraryPath: libraryPath,
                selectedEntityId: kgFocusState.focusedEntityId,
                selectedClaimId: kgFocusState.focusedClaimId ?? claimFocusState.selectedClaimId,
                activePageNumber: activePageNumber,
                pageCount: pageCount,
                onPageSelected: onPageSelected,
                scrollSync: scrollSync
            )
        } else {
            VStack(spacing: 8) {
                Spacer()
                // User-facing name for this pane. The internal type is
                // DocumentKGWebPane / DocumentKGSurface, but the user only ever
                // sees "Knowledge" (and the Transcript/Digest/Graph tab strip
                // when a document is loaded) — the internal name never leaks. (#1450)
                Text("Knowledge")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Select a document with extracted knowledge to view transcript, digest, and graph.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 220)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
        }
    }
}
