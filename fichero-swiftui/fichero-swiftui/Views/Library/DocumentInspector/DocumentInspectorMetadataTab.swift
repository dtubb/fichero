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

            // Dynamic metadata fields (filter out noisy fields)
            ForEach(Array(document.metadata.keys.sorted().filter { !hiddenMetadataKeys.contains($0) }),
                    id: \.self) { key in
                if let value = document.metadata[key] {
                    LabeledContent(formatMetadataKey(key)) {
                        Text(formatMetadataValue(key: key, value: value.value))
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

    private let hiddenMetadataKeys: Set<String> = [
        "Checksum", "checksum", "hash", "md5", "sha256",
        "Mime_Type", "mime_type", "MimeType", "content_type",
        "Width", "Height", "width", "height",
        "page_content", "page_content_rtf",
        "transcription", "Transcription"
    ]

    private func formatMetadataKey(_ key: String) -> String {
        key.replacingOccurrences(of: "_", with: " ")
           .components(separatedBy: " ")
           .map { $0.capitalized }
           .joined(separator: " ")
    }

    private func formatMetadataValue(key: String, value: Any) -> String {
        let lowerKey = key.lowercased()
        if lowerKey.contains("size") || lowerKey.contains("bytes") {
            if let intVal = value as? Int {
                return ByteCountFormatter.string(fromByteCount: Int64(intVal), countStyle: .file)
            }
            if let strVal = value as? String, let intVal = Int(strVal) {
                return ByteCountFormatter.string(fromByteCount: Int64(intVal), countStyle: .file)
            }
        }
        return String(describing: value)
    }
}
