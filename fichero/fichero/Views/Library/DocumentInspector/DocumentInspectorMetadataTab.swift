import SwiftUI

/// Metadata tab — two-step progressive disclosure: name + truncated value, select to expand full value.
struct DocumentInspectorMetadataTab: View {
    let document: Document

    @State private var selectedKey: String?

    var body: some View {
        List(selection: $selectedKey) {
            if let path = document.path {
                MetadataAttributeRow(
                    name: "Path",
                    summary: abbreviate(path),
                    fullValue: path,
                    isSelected: selectedKey == pathRowTag
                )
                .tag(pathRowTag)
            }

            ForEach(filteredKeys, id: \.self) { key in
                if let entry = document.metadata[key] {
                    let formatted = formatMetadataValue(key: key, value: entry.value)
                    MetadataAttributeRow(
                        name: formatMetadataKey(key),
                        summary: abbreviate(formatted),
                        fullValue: formatted,
                        isSelected: selectedKey == key
                    )
                    .tag(key)
                }
            }

            if document.metadata.isEmpty && document.path == nil {
                Text("No metadata available")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .italic()
            }
        }
        .listStyle(.inset)
        .onChange(of: document.id) { _, _ in selectedKey = nil }
    }

    // MARK: - Helpers

    private let pathRowTag = "__path__"

    private var filteredKeys: [String] {
        document.metadata.keys.sorted().filter { !hiddenMetadataKeys.contains($0) }
    }

    private let hiddenMetadataKeys: Set<String> = [
        "Checksum", "checksum", "hash", "md5", "sha256",
        "Mime_Type", "mime_type", "MimeType", "content_type",
        "Width", "Height", "width", "height",
        "page_content", "page_content_rtf",
        "transcription", "Transcription"
    ]

    private func abbreviate(_ str: String, max: Int = 50) -> String {
        str.count <= max ? str : String(str.prefix(max)) + "…"
    }

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

// MARK: - Row view

private struct MetadataAttributeRow: View {
    let name: String
    let summary: String
    let fullValue: String
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: isSelected ? 6 : 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(name)
                    .fontWeight(.medium)
                Spacer()
                if !isSelected {
                    Text(summary)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            if isSelected {
                Text(fullValue)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(.vertical, 2)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }
}
