import AppKit
import SwiftUI

/// Content tab for DocumentInspector showing extracted text content
struct DocumentInspectorContentTab: View {
    let document: Document
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore
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

    private var documentSignature: String {
        signature(
            id: document.id,
            updatedAt: document.updatedAt,
            pageContent: document.pageContent,
            richTextBase64: document.metadata[Self.richTextMetadataKey]?.value as? String
        )
    }

    var body: some View {
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

            if draftContent.isEmpty {
                Text("Add notes or edit extracted text...")
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 14)
                    .allowsHitTesting(false)
            }

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
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            loadDraft(from: document)
        }
        .onDisappear {
            autoSaveTask?.cancel()
            autoSaveTask = nil
        }
        .onChange(of: documentSignature) { _, newSignature in
            guard newSignature != lastLoadedSignature else { return }
            if isEditingText && hasChanges {
                pendingExternalSignature = newSignature
                return
            }
            loadDraft(from: document)
            saveError = nil
        }
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

        // Ensure text remains visible in all appearances.
        mutable.addAttribute(.foregroundColor, value: NSColor.labelColor, range: fullRange)
        if mutable.attribute(.font, at: 0, effectiveRange: nil) == nil {
            mutable.addAttribute(.font, value: NSFont.systemFont(ofSize: NSFont.systemFontSize), range: fullRange)
        }
        return mutable
    }
}

private struct AttributedTextEditor: NSViewRepresentable {
    @Binding var text: NSAttributedString
    let isEditable: Bool
    let rulersVisible: Bool
    let fontName: String
    let fontSize: Double
    let lineSpacing: Double
    let marginH: Double
    let marginV: Double
    let contentRevision: Int
    let onTextChanged: () -> Void
    let onEditingChanged: (Bool) -> Void

    private var resolvedFont: NSFont {
        if fontName == "System" {
            return .systemFont(ofSize: CGFloat(fontSize))
        }
        return NSFont(name: fontName, size: CGFloat(fontSize))
            ?? .systemFont(ofSize: CGFloat(fontSize))
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.hasHorizontalRuler = true
        scrollView.rulersVisible = rulersVisible
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = true
        scrollView.backgroundColor = .textBackgroundColor

        let textView = NSTextView()
        textView.isEditable = isEditable
        textView.isSelectable = true
        textView.isRichText = true
        textView.usesRuler = true
        textView.usesFontPanel = true
        textView.importsGraphics = false
        textView.allowsUndo = true
        textView.isAutomaticTextCompletionEnabled = true
        textView.isContinuousSpellCheckingEnabled = true
        textView.isGrammarCheckingEnabled = true
        textView.isAutomaticSpellingCorrectionEnabled = true
        textView.drawsBackground = true
        textView.backgroundColor = .textBackgroundColor
        textView.textColor = .labelColor
        textView.font = resolvedFont
        textView.textContainerInset = NSSize(width: marginH, height: marginV)
        textView.defaultParagraphStyle = {
            let style = NSMutableParagraphStyle()
            style.lineSpacing = CGFloat(lineSpacing)
            return style
        }()
        textView.textContainer?.widthTracksTextView = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.delegate = context.coordinator
        textView.textStorage?.setAttributedString(text)

        scrollView.documentView = textView
        context.coordinator.textView = textView
        context.coordinator.lastAppliedRevision = contentRevision
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        textView.isEditable = isEditable
        scrollView.rulersVisible = rulersVisible

        // Apply typography settings
        textView.font = resolvedFont
        textView.textContainerInset = NSSize(width: marginH, height: marginV)
        let paraStyle = NSMutableParagraphStyle()
        paraStyle.lineSpacing = CGFloat(lineSpacing)
        textView.defaultParagraphStyle = paraStyle

        // Only push model text into AppKit view on explicit revision changes.
        // This avoids clobbering active edits and selection.
        if context.coordinator.lastAppliedRevision != contentRevision {
            let selectedRanges = textView.selectedRanges
            context.coordinator.isApplyingModelUpdate = true
            textView.textStorage?.setAttributedString(text)
            textView.setSelectedRanges(
                selectedRanges,
                affinity: textView.selectionAffinity,
                stillSelecting: false
            )
            context.coordinator.lastAppliedRevision = contentRevision
            context.coordinator.isApplyingModelUpdate = false
        }
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: NSAttributedString
        weak var textView: NSTextView?
        var isApplyingModelUpdate = false
        var lastAppliedRevision = 0
        let onTextChanged: () -> Void
        let onEditingChanged: (Bool) -> Void

        init(
            text: Binding<NSAttributedString>,
            onTextChanged: @escaping () -> Void,
            onEditingChanged: @escaping (Bool) -> Void
        ) {
            _text = text
            self.onTextChanged = onTextChanged
            self.onEditingChanged = onEditingChanged
        }

        func textDidChange(_ notification: Notification) {
            guard let textView else { return }
            guard !isApplyingModelUpdate else { return }
            text = textView.attributedString()
            onTextChanged()
        }

        func textDidBeginEditing(_ notification: Notification) {
            onEditingChanged(true)
        }

        func textDidEndEditing(_ notification: Notification) {
            onEditingChanged(false)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text,
            onTextChanged: onTextChanged,
            onEditingChanged: onEditingChanged
        )
    }
}
