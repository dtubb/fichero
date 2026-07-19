import SwiftUI

// MARK: - Page Content Pane (#1189)

/// Displays the transcription / page_content text for the selected page document.
struct PageContentPane: View {
    let document: Document?

    @Environment(ClaimFocusState.self) private var claimFocusState
    @Environment(DocumentService.self) private var documentService
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

    static let claimSourceHighlightId = "claim-source-highlight"

    private var pageDoc: Document? {
        guard let doc = document, doc.docType == .page else { return nil }
        return doc
    }

    /// Decoded, display-ready page text. RTF source is resolved to plain text so
    /// the reader never shows raw `\'e1`/control-word escapes (#2317); everything
    /// downstream (edit draft, highlight ranges, claim matching) works off this
    /// same decoded string so offsets stay consistent.
    private var pageContent: String {
        ArtifactRichTextCodec.plainText(pageDoc?.pageContent ?? "")
    }

    var body: some View {
        VStack(spacing: 0) {
            if pageDoc != nil {
                if editState.isEditing {
                    TextEditor(text: $editState.draftContent)
                        .editorScaledFont(.body, design: .serif)
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
                } else if !pageContent.isEmpty {
                    pageContentScroll(pageContent)
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
                    onNote: beginNote,
                    onStar: addStar,
                    onBookmark: addBookmark
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

            // Bottom-anchored mini-toolbar (#3060 / #2670): the Content/Edit bar
            // matches every other pane's bottom bar — content above, bar below.
            Divider()
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
        }
        .background(Color(.textBackgroundColor))
        .onAppear {
            editState.synchronize(with: pageContent)
            loadAnnotations()
            // Apply any already-selected claim's source highlight on appear, not
            // only on change — so switching to the Page transcript after picking
            // a claim in the Knowledge tab reveals the highlight (#3511).
            syncSourceHighlightFromClaimFocus()
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
        .onChange(of: claimFocusState.selectedClaimId) { _, _ in syncSourceHighlightFromClaimFocus() }
        .onChange(of: claimFocusState.selectedClaimSourceDocumentId) { _, _ in syncSourceHighlightFromClaimFocus() }
        .onChange(of: claimFocusState.selectedClaimText) { _, _ in syncSourceHighlightFromClaimFocus() }
        .onChange(of: claimFocusState.selectedClaimCharStart) { _, _ in syncSourceHighlightFromClaimFocus() }
        .onChange(of: claimFocusState.selectedClaimCharEnd) { _, _ in syncSourceHighlightFromClaimFocus() }
    }
}
