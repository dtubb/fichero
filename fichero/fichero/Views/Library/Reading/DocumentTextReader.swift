import SwiftUI

struct PageContentPaneEditState {
    var isEditing = false
    var draftContent = ""
    var savedContent = ""

    mutating func synchronize(with content: String) {
        guard !isEditing else { return }
        draftContent = content
        savedContent = content
    }

    mutating func beginEditing(from content: String) {
        draftContent = content
        savedContent = content
        isEditing = true
    }

    mutating func markSaved() {
        savedContent = draftContent
    }

    var hasUnsavedChanges: Bool {
        draftContent != savedContent
    }

    func shouldSaveOnBlur(isFocused: Bool) -> Bool {
        isEditing && !isFocused && hasUnsavedChanges
    }
}

struct PageContentClaimSourceHighlight: Equatable {
    let before: String
    let highlighted: String
    let after: String

    static func match(content: String, documentId: String, info: [AnyHashable: Any]) -> Self? {
        guard let infoDocumentId = info["documentId"] as? String,
              infoDocumentId == documentId,
              !content.isEmpty else { return nil }

        if let charRange = charRange(in: content, info: info) {
            return split(content: content, range: charRange)
        }

        let excerpt = ((info["excerpt"] as? String) ?? (info["claimText"] as? String))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard let excerpt, !excerpt.isEmpty,
              let range = content.range(
                of: excerpt,
                options: [.caseInsensitive, .diacriticInsensitive]
              ) else { return nil }
        return split(content: content, range: range)
    }

    private static func charRange(in content: String, info: [AnyHashable: Any]) -> Range<String.Index>? {
        let start = intValue(info["charStart"])
        let end = intValue(info["charEnd"])
        guard let start, let end, start >= 0, end > start, end <= content.utf16.count else {
            return nil
        }
        let lower = String.Index(utf16Offset: start, in: content)
        let upper = String.Index(utf16Offset: end, in: content)
        guard lower < upper else { return nil }
        return lower..<upper
    }

    private static func intValue(_ value: Any?) -> Int? {
        if let int = value as? Int { return int }
        if let number = value as? NSNumber { return number.intValue }
        return nil
    }

    private static func split(content: String, range: Range<String.Index>) -> Self {
        Self(
            before: String(content[..<range.lowerBound]),
            highlighted: String(content[range]),
            after: String(content[range.upperBound...])
        )
    }
}

/// Annotatable text reader for whole-document text (txt / docx / md), #2458
/// slice 3. Reuses the slice-1 components — `AnnotatableTextView` (selectable
/// text + saved-highlight rendering), `AnnotationToolbar`, and the pure
/// `AnnotationHighlight` range math — scoped to the document rather than a PDF
/// page (which `PageContentPane` already covers).
struct DocumentTextReader: View {
    let document: Document
    let content: String

    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore
    @State private var selectionRange: Range<Int>?
    @State private var isComposingNote = false
    @State private var noteDraft = ""

    var body: some View {
        VStack(spacing: 0) {
            AnnotatableTextView(
                text: content,
                highlights: highlightRanges,
                selection: $selectionRange
            )
            Divider()
            AnnotationToolbar(
                canAnnotateSelection: selectionRange != nil,
                savedCount: documentAnnotations.count,
                onHighlight: addHighlight,
                onNote: beginNote
            )
            .popover(isPresented: $isComposingNote, arrowEdge: .bottom) {
                noteComposer
            }
        }
        .background(Color(.textBackgroundColor))
        .onAppear { loadAnnotations() }
        .onChange(of: document.id) { _, _ in
            selectionRange = nil
            loadAnnotations()
        }
        .onChange(of: annotationStore.changeToken) { _, _ in loadAnnotations() }
    }

    // MARK: - Annotations

    private var documentAnnotations: [DocumentAnnotation] {
        annotationStore.annotations.filter { $0.documentId == document.id }
    }

    private var highlightRanges: [Range<Int>] {
        AnnotationHighlight.ranges(
            for: documentAnnotations,
            inUTF16Count: (content as NSString).length
        )
    }

    private func loadAnnotations() {
        Task { await annotationStore.loadAnnotations(for: .document(document.id), force: true) }
    }

    private func selectedText(_ range: Range<Int>) -> String {
        let nsContent = content as NSString
        let nsRange = NSRange(location: range.lowerBound, length: range.count)
        guard NSMaxRange(nsRange) <= nsContent.length else { return "" }
        return nsContent.substring(with: nsRange)
    }

    private func addHighlight() {
        guard let range = selectionRange else { return }
        let quoted = selectedText(range)
        Task {
            _ = await annotationStore.addNote(
                scope: .document(document.id),
                text: quoted,
                charStart: range.lowerBound,
                charEnd: range.upperBound,
                kind: .highlight
            )
            await annotationStore.loadAnnotations(for: .document(document.id), force: true)
        }
    }

    private func beginNote() {
        noteDraft = ""
        isComposingNote = true
    }

    private func saveNote() {
        let trimmed = noteDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { isComposingNote = false; return }
        let range = selectionRange
        isComposingNote = false
        Task {
            _ = await annotationStore.addNote(
                scope: .document(document.id),
                text: trimmed,
                charStart: range?.lowerBound,
                charEnd: range?.upperBound,
                kind: .note
            )
            await annotationStore.loadAnnotations(for: .document(document.id), force: true)
        }
    }

    private var noteComposer: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(selectionRange != nil ? "Note on selection" : "Note on document")
                .font(.headline)
            TextField("Note", text: $noteDraft, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(3...6)
                .frame(width: 260)
            HStack {
                Spacer()
                Button("Cancel") { isComposingNote = false }
                Button("Save", action: saveNote)
                    .keyboardShortcut(.defaultAction)
                    .disabled(noteDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(12)
    }
}
