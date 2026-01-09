import SwiftUI

// MARK: - Scoped Document Row

/// Row view for displaying a document in the chat scope list
struct ScopedDocumentRow: View {
    let document: Document

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: document.fileType?.icon ?? "doc")
                .foregroundColor(.secondary)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(document.name)
                    .font(.subheadline)
                    .lineLimit(1)

                if let fileType = document.fileType {
                    Text(fileType.rawValue.capitalized)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }
}

// MARK: - Preview

#Preview {
    List {
        ScopedDocumentRow(document: Document(
            id: "1",
            name: "Sample Document.pdf",
            path: "/sample",
            docType: .file,
            fileType: .pdf
        ))
        ScopedDocumentRow(document: Document(
            id: "2",
            name: "Another File.txt",
            path: "/another",
            docType: .file,
            fileType: .text
        ))
    }
    .frame(width: 250, height: 200)
}
