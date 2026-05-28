import SwiftUI

extension ContentView {
    @ViewBuilder
    func knowledgeSurface(for document: Document?, activePageNumber: Int?) -> some View {
        if let document, let libraryPath = apiClient.currentLibraryPath, !libraryPath.isEmpty {
            DocumentKGSurface(
                documentId: document.id,
                libraryPath: libraryPath,
                selectedClaimId: claimFocusState.selectedClaimId,
                activePageNumber: activePageNumber
            )
        } else {
            VStack(spacing: 8) {
                Spacer()
                Text("Knowledge Surface")
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
