import AppKit
import SwiftUI

/// State management for DocumentInspectorContentTab
@MainActor
final class DocumentInspectorContentState: ObservableObject {
    @Published var draftAttributedText = NSAttributedString(string: "")
    @Published var originalPlainContent: String = ""
    @Published var originalRTFBase64: String = ""
    @Published var lastLoadedSignature: String = ""
    @Published var pendingExternalSignature: String?
    @Published var isEditingText = false
    @Published var editorRevision = 0
    @Published var isSaving = false
    @Published var saveError: String?
    @Published var lastSavedPayloadSignature: String = ""
    @Published var availableFonts: [String] = []

    private static let richTextMetadataKey = "page_content_rtf"

    var draftContent: String { draftAttributedText.string }

    var currentRTFBase64: String {
        encodeRTFBase64(from: draftAttributedText)
    }

    var hasChanges: Bool {
        draftContent != originalPlainContent || currentRTFBase64 != originalRTFBase64
    }

    var draftPayloadSignature: String {
        "\(draftContent)|\(currentRTFBase64)"
    }

    func documentSignature(for doc: Document) -> String {
        signature(
            id: doc.id,
            updatedAt: doc.updatedAt,
            pageContent: doc.pageContent,
            richTextBase64: doc.metadata[Self.richTextMetadataKey]?.value as? String
        )
    }

    func loadDraft(from doc: Document) {
        let plainText = doc.pageContent ?? ""
        let metadataValue = doc.metadata[Self.richTextMetadataKey]?.value as? String
        let richText = normalizeForEditor(
            decodeRTF(base64: metadataValue) ?? NSAttributedString(string: plainText)
        )

        draftAttributedText = richText
        originalPlainContent = plainText
        originalRTFBase64 = metadataValue ?? ""
        lastSavedPayloadSignature = "\(plainText)|\(metadataValue ?? "")"
        lastLoadedSignature = signature(
            id: doc.id,
            updatedAt: doc.updatedAt,
            pageContent: doc.pageContent,
            richTextBase64: metadataValue
        )
        pendingExternalSignature = nil
        editorRevision += 1
    }

    func saveContent(
        document: Document,
        documentService: DocumentServiceGenerated,
        documentStore: DocumentStore
    ) async {
        guard !isSaving, hasChanges else { return }
        guard draftPayloadSignature != lastSavedPayloadSignature else { return }
        isSaving = true
        saveError = nil

        var metadataPayload = document.metadata.mapValues { convertToSendable($0.value) }
        metadataPayload[Self.richTextMetadataKey] = currentRTFBase64

        do {
            let updated = try await documentService.updateDocument(
                document.id,
                metadataPayload: metadataPayload,
                pageContent: draftContent
            )
            documentStore.updateLocal(updated)
            documentStore.publish(.documentsUpdated(documentStore.currentDocuments))
            loadDraft(from: updated)
            lastSavedPayloadSignature = draftPayloadSignature
            pendingExternalSignature = nil
        } catch {
            saveError = "Failed to save text: \(error.localizedDescription)"
        }
        isSaving = false
    }

    private func decodeRTF(base64: String?) -> NSAttributedString? {
        guard let base64, !base64.isEmpty,
              let data = Data(base64Encoded: base64) else { return nil }
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
        ) else { return "" }
        return data.base64EncodedString()
    }

    private func convertToSendable(_ value: Any) -> any Sendable {
        switch value {
        case let bool as Bool: return bool
        case let int as Int: return int
        case let double as Double: return double
        case let string as String: return string
        case let array as [Any]: return array.map { convertToSendable($0) }
        case let dict as [String: Any]: return dict.mapValues { convertToSendable($0) }
        default: return String(describing: value)
        }
    }

    private func signature(
        id: String,
        updatedAt: Date,
        pageContent: String?,
        richTextBase64: String?
    ) -> String {
        "\(id)|\(updatedAt.timeIntervalSince1970)|\(pageContent ?? "")|\(richTextBase64 ?? "")"
    }

    private func normalizeForEditor(_ attributed: NSAttributedString) -> NSAttributedString {
        let mutable = NSMutableAttributedString(attributedString: attributed)
        guard mutable.length > 0 else { return mutable }
        let fullRange = NSRange(location: 0, length: mutable.length)
        mutable.addAttribute(.foregroundColor, value: NSColor.labelColor, range: fullRange)
        if mutable.attribute(.font, at: 0, effectiveRange: nil) == nil {
            mutable.addAttribute(.font, value: NSFont.systemFont(ofSize: NSFont.systemFontSize), range: fullRange)
        }
        return mutable
    }
}
