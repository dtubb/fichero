import AppKit
import SwiftUI

/// Content tab for DocumentInspector showing extracted text content
struct DocumentInspectorContentTab: View {
    let document: Document
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @AppStorage("editor.rulersVisible") private var rulersVisible = true
    @AppStorage("editor.fontName") private var fontName: String = "System"
    @AppStorage("editor.fontSize") private var fontSize: Double = 14
    @AppStorage("editor.lineSpacing") private var lineSpacing: Double = 4
    @AppStorage("editor.marginHorizontal") private var marginH: Double = 16
    @AppStorage("editor.marginVertical") private var marginV: Double = 12

    @State private var draftAttributedText = NSAttributedString(string: "")
    @State private var originalPlainContent: String = ""
    @State private var originalRTFBase64: String = ""
    @State private var lastLoadedSignature: String = ""
    @State private var pendingExternalSignature: String?
    @State private var isEditingText = false
    @State private var editorRevision = 0
    @State private var isSaving = false
    @State private var autoSaveTask: Task<Void, Never>?
    @State private var saveError: String?
    @State private var lastSavedPayloadSignature: String = ""

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

    private var draftPayloadSignature: String {
        "\(draftContent)|\(currentRTFBase64)"
    }

    private var documentSignature: String {
        signature(
            id: document.id,
            updatedAt: document.updatedAt,
            pageContent: document.pageContent,
            richTextBase64: document.metadata[Self.richTextMetadataKey]?.value as? String
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .topLeading) {
                AttributedTextEditor(
                    text: $draftAttributedText,
                    isEditable: !isSaving,
                    rulersVisible: rulersVisible,
                    fontName: fontName,
                    fontSize: fontSize,
                    lineSpacing: lineSpacing,
                    marginH: marginH,
                    marginV: marginV,
                    contentRevision: editorRevision,
                    onTextChanged: {
                        scheduleAutoSave()
                        saveError = nil
                    },
                    onEditingChanged: { isEditing in
                        isEditingText = isEditing
                        if !isEditing {
                            scheduleAutoSave(immediate: true)
                        }
                        if !isEditing, pendingExternalSignature != nil, !hasChanges {
                            loadDraft(from: document)
                            saveError = nil
                        }
                    }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(.textBackgroundColor))

                if let saveError {
                    Text(saveError)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(8)
                        .background(.regularMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .padding(8)
                } else if isSaving {
                    HStack(spacing: 6) {
                        ProgressView()
                            .controlSize(.small)
                        Text("Saving...")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .padding(8)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            loadDraft(from: document)
        }
        .onDisappear {
            // NEVER cancel — let any pending debounce fire so the user's edits
            // aren't silently lost on navigation. If there are unflushed changes,
            // fire an immediate save that runs independently of this view's lifecycle.
            autoSaveTask = nil
            if hasChanges {
                Task { @MainActor in await saveContent() }
            }
        }
        .onChange(of: documentSignature) { _, newSignature in
            guard newSignature != lastLoadedSignature else { return }
            // Preserve any unsaved changes regardless of focus state — a user who
            // clicked outside the text view still expects their draft to survive.
            if hasChanges {
                pendingExternalSignature = newSignature
                return
            }
            loadDraft(from: document)
            saveError = nil
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            Task { await refreshDocumentFromBackend() }
        }
    }

    private func refreshDocumentFromBackend() async {
        // Don't race with an in-flight save — the save's updateLocal call wins.
        guard !isSaving else { return }
        guard let fresh = try? await documentService.getDocument(document.id) else { return }
        // Only apply if the backend has strictly newer data than what we loaded last.
        // This prevents a stale fetch from overwriting a just-completed user save.
        guard fresh.updatedAt > document.updatedAt else { return }
        documentStore.refreshLocalContent(fresh)
    }

    // MARK: - Persistence

    private func scheduleAutoSave(immediate: Bool = false) {
        autoSaveTask?.cancel()
        autoSaveTask = Task { @MainActor in
            if !immediate {
                try? await Task.sleep(nanoseconds: 600_000_000)
            }
            guard !Task.isCancelled else { return }
            await saveContent()
        }
    }

    private func saveContent() async {
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
            // refreshLocalContent, not updateLocal — a content save never moves the
            // document between folders, so don't run the cross-folder removal branch
            // that updateLocal applies when parentId != selectedCollection.
            documentStore.refreshLocalContent(updated)
            loadDraft(from: updated)
            lastSavedPayloadSignature = draftPayloadSignature
            pendingExternalSignature = nil
        } catch {
            saveError = "Failed to save text: \(error.localizedDescription)"
        }
        isSaving = false
    }

    private func loadDraft(from doc: Document) {
        let plainText = doc.pageContent ?? ""
        let metadataValue = doc.metadata[Self.richTextMetadataKey]?.value as? String
        let richText = normalizeForEditor(
            decodeRTF(base64: metadataValue) ?? NSAttributedString(string: plainText)
        )

        draftAttributedText = richText
        originalPlainContent = plainText
        originalRTFBase64 = metadataValue ?? ""
        lastSavedPayloadSignature = "\(plainText)|\(metadataValue ?? "")"
        lastLoadedSignature = signature(for: doc)
        pendingExternalSignature = nil
        editorRevision += 1
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

    private func signature(for doc: Document) -> String {
        signature(
            id: doc.id,
            updatedAt: doc.updatedAt,
            pageContent: doc.pageContent,
            richTextBase64: doc.metadata[Self.richTextMetadataKey]?.value as? String
        )
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
        guard mutable.length > 0 else {
            // Keep empty content truly empty; typing attributes are provided by NSTextView config.
            return mutable
        }
        let fullRange = NSRange(location: 0, length: mutable.length)

        // Only fill in defaults for ranges with no explicit attribute; never overwrite
        // the user's foreground color or font chosen via the format menu.
        mutable.enumerateAttribute(.foregroundColor, in: fullRange, options: []) { value, range, _ in
            if value == nil {
                mutable.addAttribute(.foregroundColor, value: NSColor.labelColor, range: range)
            }
        }
        mutable.enumerateAttribute(.font, in: fullRange, options: []) { value, range, _ in
            if value == nil {
                mutable.addAttribute(
                    .font,
                    value: NSFont.systemFont(ofSize: NSFont.systemFontSize),
                    range: range
                )
            }
        }
        return mutable
    }
}
