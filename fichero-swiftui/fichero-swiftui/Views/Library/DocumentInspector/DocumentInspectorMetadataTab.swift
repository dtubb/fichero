import SwiftUI

/// Metadata tab content for DocumentInspector
struct DocumentInspectorMetadataTab: View {
    let document: Document

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Technical Metadata")
                .font(.subheadline)
                .fontWeight(.semibold)

            if let path = document.path {
                LabeledContent("Path") {
                    Text(path)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                .textSelection(.enabled)
            }

            // Dynamic metadata fields
            ForEach(Array(document.metadata.keys.sorted()), id: \.self) { key in
                if let value = document.metadata[key] {
                    LabeledContent(formatMetadataKey(key)) {
                        Text(String(describing: value.value))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .textSelection(.enabled)
                }
            }

            if document.metadata.isEmpty && document.path == nil {
                Text("No metadata available")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
    }

    // MARK: - Helpers

    private func formatMetadataKey(_ key: String) -> String {
        // Convert "Exif_Make" to "Make", "File_Size" to "Size", etc.
        key.replacingOccurrences(of: "_", with: " ")
           .components(separatedBy: " ")
           .map { $0.capitalized }
           .joined(separator: " ")
    }
}
