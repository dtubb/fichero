import SwiftUI

/// Info tab content for DocumentInspector
struct DocumentInspectorInfoTab: View {
    let document: Document

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            headerSection
            Divider()
            statusSection
            Divider()
            basicFileInfo
        }
    }

    // MARK: - Header Section

    private var headerSection: some View {
        VStack(alignment: .center, spacing: 12) {
            // Thumbnail from backend
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

            // Name
            Text(document.name)
                .font(.headline)
                .multilineTextAlignment(.center)
                .lineLimit(3)

            // Type badge
            HStack(spacing: 4) {
                Text(document.docType.rawValue.capitalized)
                    .font(.caption)
                    .foregroundColor(.secondary)

                if let fileType = document.fileType {
                    Text("•")
                        .foregroundColor(.secondary)
                    Text(fileType.rawValue.capitalized)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Status Section

    private var statusSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Status")
                .font(.subheadline)
                .fontWeight(.semibold)

            HStack {
                StatusBadge(status: document.status)
                Spacer()

                if document.status == .processing {
                    ProgressView()
                        .scaleEffect(0.7)
                }
            }

            // Dates
            LabeledContent("Created") {
                Text(document.createdAt, style: .date)
                    .font(.caption)
            }

            LabeledContent("Modified") {
                Text(document.updatedAt, style: .relative)
                    .font(.caption)
            }
        }
    }

    // MARK: - Basic File Info

    private var basicFileInfo: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("File Information")
                .font(.subheadline)
                .fontWeight(.semibold)

            if let fileType = document.fileType {
                LabeledContent("Type") {
                    Text(fileType.rawValue.capitalized)
                        .font(.caption)
                }
            }

            if let fileSize = document.metadata["File_Size"]?.value as? Int {
                LabeledContent("Size") {
                    Text(ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file))
                        .font(.caption)
                }
            }

            if let width = document.metadata["Width"]?.value as? Int,
               let height = document.metadata["Height"]?.value as? Int {
                LabeledContent("Dimensions") {
                    Text("\(width) × \(height)")
                        .font(.caption)
                }
            }
        }
    }
}
