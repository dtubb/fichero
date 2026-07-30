import SwiftUI

extension DocumentInspectorInfoTab {
    var headerSection: some View {
        VStack(alignment: .center, spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.windowBackgroundColor))
                    .frame(width: 80, height: 100)

                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 80, height: 100)
                    .clipped()
            }
            .frame(width: 80, height: 100)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            // Never `document.name`: a page's is a storage artifact (#4416).
            Text(DocumentTitle.displayName(for: document))
                .font(.headline)
                .multilineTextAlignment(.center)
                .lineLimit(3)

            Button {
                Task { await toggleExcludeFromProcessing() }
            } label: {
                if isUpdatingExclude {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Label(
                        isExcludedFromProcessing ? "Include in Processing" : "Exclude from Processing",
                        systemImage: isExcludedFromProcessing ? "eye" : "eye.slash"
                    )
                }
            }
            .buttonStyle(.bordered)
            .disabled(isUpdatingExclude)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }
}
