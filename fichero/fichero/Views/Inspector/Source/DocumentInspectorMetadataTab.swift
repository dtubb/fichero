import SwiftUI

/// Metadata tab — two-step progressive disclosure: name + truncated value, select to expand full value.
struct DocumentInspectorMetadataTab: View {
    let document: Document

    @State private var selectedKey: String?

    var body: some View {
        // NOT a `List`, for the reason its neighbour already documents: this
        // view is hosted inside `SourceInfoView`'s `ScrollView`, and a SwiftUI
        // `List` collapses to zero height inside a `ScrollView` (#2107). That
        // is why `DocumentInspectorInfoTab` was rewritten to plain stacks; this
        // tab was the same shape and never got the treatment, so the metadata
        // body rendered at zero height while the Info block above it looked
        // fine (#4502).
        //
        // Rows are `Button`s rather than the tap gestures the Info tab used.
        // Same progressive disclosure, but a button is focusable, reachable by
        // keyboard, announced as a button by VoiceOver, and gives a real touch
        // target on iPad — none of which a bare `.onTapGesture` on a stack row
        // does.
        VStack(alignment: .leading, spacing: 0) {
            if let path = document.path {
                metadataRow(tag: pathRowTag, name: "Path", value: path)
            }

            ForEach(filteredKeys, id: \.self) { key in
                if let entry = document.metadata[key] {
                    metadataRow(
                        tag: key,
                        name: formatMetadataKey(key),
                        value: formatMetadataValue(key: key, value: entry.value)
                    )
                }
            }

            if document.metadata.isEmpty && document.path == nil {
                Text("No metadata available")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .italic()
            }
        }
        .onChange(of: document.id) { _, _ in selectedKey = nil }
    }

    /// One metadata row: selecting it expands the full value, selecting it
    /// again collapses it. The toggle is deliberate — with no `List` there is
    /// no row deselection to fall back on, and a row that could only ever open
    /// would leave the user no way to close it.
    @ViewBuilder
    private func metadataRow(tag: String, name: String, value: String) -> some View {
        Button {
            selectedKey = (selectedKey == tag) ? nil : tag
        } label: {
            MetadataAttributeRow(
                name: name,
                summary: abbreviate(value),
                fullValue: value,
                isSelected: selectedKey == tag
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selectedKey == tag ? [.isSelected] : [])
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
