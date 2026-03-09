import AppKit
import SwiftUI

/// Content tab for DocumentInspector showing extracted text content
struct DocumentInspectorContentTab: View {
    let document: Document
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore

    @State private var draftAttributedText = NSAttributedString(string: "")
    @State private var originalPlainContent: String = ""
    @State private var originalRTFBase64: String = ""
    @State private var isSaving = false
    @State private var saveError: String?

    private static let richTextMetadataKey = "page_content_rtf"

    private var draftContent: String {
        draftAttributedText.string
    }

    private var currentRTFBase64: String {
        encodeRTFBase64(from: draftAttributedText)
    }

    private var hasChanges: Bool {
        draftContent != originalPlainContent || currentRTFBase64 != originalRTFBase64
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Text")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                if !draftContent.isEmpty {
                    Button(
                        action: { copyToClipboard(draftContent) },
                        label: {
                            Image(systemName: "doc.on.doc")
                        }
                    )
                    .buttonStyle(.plain)
                    .help("Copy to clipboard")
                }

                if hasChanges {
                    Button("Revert") {
                        loadDraft(from: document)
                        saveError = nil
                    }
                    .buttonStyle(.borderless)
                    .disabled(isSaving)

                    Button("Save") {
                        saveContent()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isSaving)
                }
            }

            ZStack(alignment: .topLeading) {
                AttributedTextEditor(text: $draftAttributedText)
                    .frame(minHeight: 220)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(6)
                    .disabled(isSaving)

                if draftContent.isEmpty {
                    Text("Add notes or edit extracted text...")
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 14)
                        .allowsHitTesting(false)
                }
            }

            if let saveError {
                Text(saveError)
                    .font(.caption)
                    .foregroundStyle(.red)
            } else if isSaving {
                HStack(spacing: 6) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Saving...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .onAppear {
            loadDraft(from: document)
        }
        .onChange(of: document.id) { _, _ in
            loadDraft(from: document)
            saveError = nil
        }
    }

    // MARK: - Clipboard

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    // MARK: - Persistence

    private func saveContent() {
        guard !isSaving else { return }
        isSaving = true
        saveError = nil

        var metadataPayload = document.metadata.mapValues { convertToSendable($0.value) }
        metadataPayload[Self.richTextMetadataKey] = currentRTFBase64

        Task { @MainActor in
            do {
                let updated = try await documentService.updateDocument(
                    document.id,
                    metadataPayload: metadataPayload,
                    pageContent: draftContent
                )
                documentStore.updateLocal(updated)
                documentStore.publish(.documentsUpdated(documentStore.currentDocuments))
                loadDraft(from: updated)
            } catch {
                saveError = "Failed to save text: \(error.localizedDescription)"
            }
            isSaving = false
        }
    }

    private func loadDraft(from doc: Document) {
        let plainText = doc.pageContent ?? ""
        let metadataValue = doc.metadata[Self.richTextMetadataKey]?.value as? String
        let richText = decodeRTF(base64: metadataValue) ?? NSAttributedString(string: plainText)

        draftAttributedText = richText
        originalPlainContent = plainText
        originalRTFBase64 = metadataValue ?? ""
    }

    private func decodeRTF(base64: String?) -> NSAttributedString? {
        guard let base64, !base64.isEmpty, let data = Data(base64Encoded: base64) else {
            return nil
        }
        return try? NSAttributedString(
            data: data,
            options: [.documentType: NSAttributedString.DocumentType.rtf],
            documentAttributes: nil
        )
    }

    private func encodeRTFBase64(from attributed: NSAttributedString) -> String {
        guard let data = try? attributed.data(
            from: NSRange(location: 0, length: attributed.length),
            documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]
        ) else {
            return ""
        }
        return data.base64EncodedString()
    }

    private func convertToSendable(_ value: Any) -> any Sendable {
        switch value {
        case let bool as Bool:
            return bool
        case let int as Int:
            return int
        case let double as Double:
            return double
        case let string as String:
            return string
        case let array as [Any]:
            return array.map { convertToSendable($0) }
        case let dict as [String: Any]:
            return dict.mapValues { convertToSendable($0) }
        default:
            return String(describing: value)
        }
    }
}

private struct AttributedTextEditor: NSViewRepresentable {
    @Binding var text: NSAttributedString

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false

        let textView = NSTextView()
        textView.isEditable = true
        textView.isRichText = true
        textView.importsGraphics = false
        textView.allowsUndo = true
        textView.usesAdaptiveColorMappingForDarkAppearance = true
        textView.drawsBackground = false
        textView.font = .systemFont(ofSize: NSFont.systemFontSize)
        textView.textContainerInset = NSSize(width: 8, height: 8)
        textView.delegate = context.coordinator
        textView.textStorage?.setAttributedString(text)

        scrollView.documentView = textView
        context.coordinator.textView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        if textView.attributedString() != text {
            textView.textStorage?.setAttributedString(text)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text)
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: NSAttributedString
        weak var textView: NSTextView?

        init(text: Binding<NSAttributedString>) {
            _text = text
        }

        func textDidChange(_ notification: Notification) {
            guard let textView else { return }
            text = textView.attributedString()
        }
    }
}
