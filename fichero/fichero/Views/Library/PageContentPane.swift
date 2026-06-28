import SwiftUI

// MARK: - Page Content Pane (#1189)

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

/// Displays the transcription / page_content text for the selected page document.
struct PageContentPane: View {
    let document: Document?

    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @Environment(DocumentStore.self) private var documentStore: DocumentStore
    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore
    @State private var editState = PageContentPaneEditState()
    @State private var sourceHighlight: PageContentClaimSourceHighlight?
    @State private var sourceHighlightToken = UUID()
    @State private var isSaving = false
    @State private var saveError: String?
    @FocusState private var isEditorFocused: Bool

    // Annotation state (#2458). The user's current text selection (UTF-16
    // offsets) drives the toolbar; `isComposingNote` presents the note popover.
    @State private var selectionRange: Range<Int>?
    @State private var isComposingNote = false
    @State private var noteDraft = ""

    private static let claimSourceHighlightId = "claim-source-highlight"

    private var pageDoc: Document? {
        guard let doc = document, doc.docType == .page else { return nil }
        return doc
    }

    private var pageContent: String {
        pageDoc?.pageContent ?? ""
    }

    var body: some View {
        VStack(spacing: 0) {
            MiniToolbar {
                Text("Content")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 0)
                if pageDoc != nil {
                    if isSaving {
                        ProgressView()
                            .controlSize(.small)
                    }
                    Button(editState.isEditing ? "Done" : "Edit") {
                        toggleEditing()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(isSaving)
                }
            }
            Divider()
            if let doc = pageDoc {
                if editState.isEditing {
                    TextEditor(text: $editState.draftContent)
                        .font(.system(.body, design: .serif))
                        .lineSpacing(4)
                        .scrollContentBackground(.hidden)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                        .padding(8)
                        .focused($isEditorFocused)
                        .onChange(of: isEditorFocused) { _, focused in
                            if editState.shouldSaveOnBlur(isFocused: focused) {
                                commitDraft(exitAfterSave: false)
                            }
                        }
                } else if let content = doc.pageContent, !content.isEmpty {
                    pageContentScroll(content)
                } else {
                    emptyState(
                        title: "No content",
                        subtitle: "Switch to Edit to add notes or a transcription."
                    )
                }
            } else {
                emptyState(
                    title: "Select a page",
                    subtitle: "Choose a PDF page to view or edit its content."
                )
            }

            // Annotation controls along the bottom of the reader (#2458).
            if pageDoc != nil, !editState.isEditing {
                Divider()
                AnnotationToolbar(
                    canAnnotateSelection: selectionRange != nil,
                    savedCount: pageAnnotations.count,
                    onHighlight: addHighlight,
                    onNote: beginNote
                )
                .popover(isPresented: $isComposingNote, arrowEdge: .bottom) {
                    noteComposer
                }
            }

            if let saveError {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text(saveError)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.orange.opacity(0.08))
            }
        }
        .background(Color(.textBackgroundColor))
        .onAppear {
            editState.synchronize(with: pageContent)
            loadAnnotations()
        }
        .onChange(of: pageDoc?.id ?? "") { _, _ in
            isSaving = false
            saveError = nil
            sourceHighlight = nil
            selectionRange = nil
            editState = PageContentPaneEditState()
            editState.synchronize(with: pageContent)
            loadAnnotations()
        }
        // Resync when an annotation.* change event lands (create/delete/edit).
        .onChange(of: annotationStore.changeToken) { _, _ in
            loadAnnotations()
        }
        .onChange(of: pageContent) { _, newContent in
            guard !editState.isEditing else { return }
            sourceHighlight = nil
            editState.synchronize(with: newContent)
        }
        .onChange(of: editState.isEditing) { _, isEditing in
            if isEditing {
                isEditorFocused = true
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .ficheroNavigateToPage)) { note in
            updateSourceHighlight(note)
        }
    }

    @ViewBuilder
    private func pageContentScroll(_ content: String) -> some View {
        if let sourceHighlight {
            // Claim-source focus keeps the SwiftUI scroll-to path so the matched
            // span centres in view (#1189). Annotation highlights resume once
            // the transient claim focus clears.
            ScrollViewReader { proxy in
                ScrollView {
                    highlightedPageContent(sourceHighlight)
                }
                .onChange(of: sourceHighlightToken) { _, _ in
                    withAnimation(.easeInOut(duration: 0.2)) {
                        proxy.scrollTo(Self.claimSourceHighlightId, anchor: .center)
                    }
                }
            }
        } else {
            // Normal reading: AppKit-backed selectable text that draws saved
            // highlights and reports the selection for the annotation toolbar.
            AnnotatableTextView(
                text: content,
                highlights: highlightRanges(for: content),
                selection: $selectionRange
            )
        }
    }

    private func highlightedPageContent(_ highlight: PageContentClaimSourceHighlight) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if !highlight.before.isEmpty {
                Text(highlight.before)
            }
            Text(highlight.highlighted)
                .padding(.horizontal, 2)
                .background(Color.yellow.opacity(0.35))
                .clipShape(RoundedRectangle(cornerRadius: 3))
                .id(Self.claimSourceHighlightId)
            if !highlight.after.isEmpty {
                Text(highlight.after)
            }
        }
        .font(.system(.body, design: .serif))
        .lineSpacing(4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
        .padding(12)
    }

    private func updateSourceHighlight(_ note: Notification) {
        guard let doc = pageDoc,
              let info = note.userInfo,
              let highlight = PageContentClaimSourceHighlight.match(
                content: pageContent,
                documentId: doc.id,
                info: info
              ) else { return }
        sourceHighlight = highlight
        sourceHighlightToken = UUID()
    }

    private func toggleEditing() {
        guard let doc = pageDoc else { return }
        saveError = nil

        if editState.isEditing {
            commitDraft(exitAfterSave: true)
        } else {
            editState.beginEditing(from: doc.pageContent ?? "")
            isEditorFocused = true
        }
    }

    private func commitDraft(exitAfterSave: Bool) {
        guard let doc = pageDoc else { return }
        guard editState.isEditing else { return }

        let draft = editState.draftContent
        guard draft != editState.savedContent else {
            if exitAfterSave {
                editState.isEditing = false
                isEditorFocused = false
            }
            saveError = nil
            return
        }

        guard !isSaving else { return }
        isSaving = true
        saveError = nil

        Task {
            let error = await persistPageContent(
                document: doc,
                content: draft,
                documentService: documentService,
                documentStore: documentStore
            )
            await MainActor.run {
                isSaving = false
                saveError = error
                if error == nil {
                    editState.markSaved()
                    if exitAfterSave {
                        editState.isEditing = false
                        isEditorFocused = false
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func emptyState(title: String, subtitle: String) -> some View {
        VStack(spacing: 8) {
            Spacer()
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(subtitle)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(12)
    }
}

// MARK: - Annotations (#2458)

extension PageContentPane {

    /// Saved annotations on the focused page (page- or document-scoped to it).
    fileprivate var pageAnnotations: [DocumentAnnotation] {
        guard let id = pageDoc?.id else { return [] }
        return annotationStore.annotations.filter { $0.pageId == id || $0.documentId == id }
    }

    /// In-bounds UTF-16 highlight ranges for the current content.
    fileprivate func highlightRanges(for content: String) -> [Range<Int>] {
        AnnotationHighlight.ranges(
            for: pageAnnotations,
            inUTF16Count: (content as NSString).length
        )
    }

    fileprivate func loadAnnotations() {
        guard let id = pageDoc?.id else { return }
        Task { await annotationStore.loadAnnotations(for: .page(id), force: true) }
    }

    /// UTF-16 substring for a selection range, used as the highlight's text.
    fileprivate func selectedText(_ range: Range<Int>) -> String {
        let nsContent = pageContent as NSString
        let nsRange = NSRange(location: range.lowerBound, length: range.count)
        guard NSMaxRange(nsRange) <= nsContent.length else { return "" }
        return nsContent.substring(with: nsRange)
    }

    fileprivate func addHighlight() {
        guard let doc = pageDoc, let range = selectionRange else { return }
        let quoted = selectedText(range)
        Task {
            _ = await annotationStore.addNote(
                scope: .page(doc.id),
                text: quoted,
                charStart: range.lowerBound,
                charEnd: range.upperBound,
                kind: .highlight
            )
            await annotationStore.loadAnnotations(for: .page(doc.id), force: true)
        }
    }

    fileprivate func beginNote() {
        noteDraft = ""
        isComposingNote = true
    }

    fileprivate func saveNote() {
        guard let doc = pageDoc else { return }
        let trimmed = noteDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { isComposingNote = false; return }
        let range = selectionRange
        isComposingNote = false
        Task {
            _ = await annotationStore.addNote(
                scope: .page(doc.id),
                text: trimmed,
                charStart: range?.lowerBound,
                charEnd: range?.upperBound,
                kind: .note
            )
            await annotationStore.loadAnnotations(for: .page(doc.id), force: true)
        }
    }

    fileprivate var noteComposer: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(selectionRange != nil ? "Note on selection" : "Note on page")
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
