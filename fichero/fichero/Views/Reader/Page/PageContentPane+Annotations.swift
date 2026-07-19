import SwiftUI

// MARK: - Annotations (#2458)

extension PageContentPane {

    /// Saved annotations on the focused page (page- or document-scoped to it).
    var pageAnnotations: [DocumentAnnotation] {
        guard let id = pageDoc?.id else { return [] }
        return annotationStore.annotations.filter { $0.pageId == id || $0.documentId == id }
    }

    /// In-bounds UTF-16 highlight ranges for the current content.
    func highlightRanges(for content: String) -> [Range<Int>] {
        AnnotationHighlight.ranges(
            for: pageAnnotations,
            inUTF16Count: (content as NSString).length
        )
    }

    func loadAnnotations() {
        guard let id = pageDoc?.id else { return }
        Task { await annotationStore.loadAnnotations(for: .page(id), force: true) }
    }

    /// UTF-16 substring for a selection range, used as the highlight's text.
    private func selectedText(_ range: Range<Int>) -> String {
        let nsContent = pageContent as NSString
        let nsRange = NSRange(location: range.lowerBound, length: range.count)
        guard NSMaxRange(nsRange) <= nsContent.length else { return "" }
        return nsContent.substring(with: nsRange)
    }

    func addHighlight() {
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
        }
    }

    /// Star the selected paragraph (or the page when nothing is selected) as a
    /// `.rating` reading mark — the paragraph-level "star" (#3548). Anchored by
    /// the selection's char range so it survives re-layout (real anchors, #3226).
    func addStar() {
        guard let doc = pageDoc else { return }
        let range = selectionRange
        let quoted = range.map(selectedText) ?? ""
        Task {
            _ = await annotationStore.addNote(
                scope: .page(doc.id),
                text: quoted,
                charStart: range?.lowerBound,
                charEnd: range?.upperBound,
                kind: .rating
            )
        }
    }

    /// Bookmark this page as a reading mark (#3548).
    func addBookmark() {
        guard let doc = pageDoc else { return }
        Task {
            _ = await annotationStore.addNote(scope: .page(doc.id), text: "", kind: .bookmark)
        }
    }

    func beginNote() {
        noteDraft = ""
        isComposingNote = true
    }

    func saveNote() {
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
        }
    }

    var noteComposer: some View {
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
