import SwiftUI

/// Inspector panel showing document metadata and details
struct InspectorView: View {
    let document: Document?

    var body: some View {
        Group {
            if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 250, maxWidth: 300)
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection(doc)

                Divider()

                // Status
                statusSection(doc)

                Divider()

                // Metadata
                metadataSection(doc)

                // Content preview
                if let content = doc.pageContent, !content.isEmpty {
                    Divider()
                    contentSection(content)
                }

                Spacer()
            }
            .padding()
        }
    }

    // MARK: - Header Section

    private func headerSection(_ doc: Document) -> some View {
        VStack(alignment: .center, spacing: 12) {
            // Thumbnail from backend
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.windowBackgroundColor))
                    .frame(width: 80, height: 100)

                AsyncImage(url: APIClient.shared.thumbnailURL(for: doc.id)) { phase in
                    switch phase {
                    case .empty:
                        ProgressView()
                            .scaleEffect(0.6)
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 80, height: 100)
                            .clipped()
                    case .failure:
                        Image(systemName: doc.fileType?.icon ?? doc.docType.icon)
                            .font(.system(size: 36))
                            .foregroundColor(.accentColor)
                    @unknown default:
                        Image(systemName: doc.fileType?.icon ?? doc.docType.icon)
                            .font(.system(size: 36))
                            .foregroundColor(.accentColor)
                    }
                }
            }
            .frame(width: 80, height: 100)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            // Name
            Text(doc.name)
                .font(.headline)
                .multilineTextAlignment(.center)
                .lineLimit(3)

            // Type badge
            HStack(spacing: 4) {
                Text(doc.docType.rawValue.capitalized)
                    .font(.caption)
                    .foregroundColor(.secondary)

                if let fileType = doc.fileType {
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

    private func statusSection(_ doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Status")
                .font(.subheadline)
                .fontWeight(.semibold)

            HStack {
                StatusBadge(status: doc.status)
                Spacer()

                if doc.status == .processing {
                    ProgressView()
                        .scaleEffect(0.7)
                }
            }

            // Dates
            LabeledContent("Created") {
                Text(doc.createdAt, style: .date)
                    .font(.caption)
            }

            LabeledContent("Modified") {
                Text(doc.updatedAt, style: .relative)
                    .font(.caption)
            }
        }
    }

    // MARK: - Metadata Section

    private func metadataSection(_ doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Metadata")
                .font(.subheadline)
                .fontWeight(.semibold)

            if let path = doc.path {
                LabeledContent("Path") {
                    Text(path)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }

            // Dynamic metadata
            ForEach(Array(doc.metadata.keys.sorted()), id: \.self) { key in
                if let value = doc.metadata[key] {
                    LabeledContent(key.capitalized) {
                        Text(String(describing: value.value))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }

            if doc.metadata.isEmpty && doc.path == nil {
                Text("No metadata available")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
    }

    // MARK: - Content Section

    private func contentSection(_ content: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Content")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                Button(action: { copyToClipboard(content) }) {
                    Image(systemName: "doc.on.doc")
                }
                .buttonStyle(.plain)
                .help("Copy to clipboard")
            }

            Text(content)
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(20)
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.textBackgroundColor))
                .cornerRadius(6)
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "sidebar.right")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Selection")
                .font(.headline)

            Text("Select a document to view details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Helpers

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

// MARK: - Preview

#Preview("Empty") {
    InspectorView(document: nil)
        .frame(width: 280, height: 400)
}
