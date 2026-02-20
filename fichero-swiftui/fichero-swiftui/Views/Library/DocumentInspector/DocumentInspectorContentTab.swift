import SwiftUI

/// Content tab for DocumentInspector showing extracted text content
struct DocumentInspectorContentTab: View {
    let document: Document

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Extracted Content")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                if let content = document.pageContent, !content.isEmpty {
                    Button(
                        action: { copyToClipboard(content) },
                        label: {
                            Image(systemName: "doc.on.doc")
                        }
                    )
                    .buttonStyle(.plain)
                    .help("Copy to clipboard")
                }
            }

            if let content = document.pageContent, !content.isEmpty {
                Text(content)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(6)
                    .textSelection(.enabled)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "doc.text")
                        .font(.title2)
                        .foregroundColor(.secondary)
                    Text("No content extracted")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("Run transcription or OCR workflow")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 32)
            }
        }
    }

    // MARK: - Clipboard

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}
