import SwiftUI

// MARK: - Page Content Pane (#1189)

/// Displays the transcription / page_content text for the selected page document.
struct PageContentPane: View {
    let document: Document?

    @Environment(ClaimFocusState.self) var claimFocusState
    @Environment(DocumentService.self) var documentService
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(AnnotationStore.self) var annotationStore: AnnotationStore
    @State var editState = PageContentPaneEditState()
    @State var sourceHighlight: PageContentClaimSourceHighlight?
    @State var sourceHighlightToken = UUID()
    @State var isSaving = false
    @State var saveError: String?
    @FocusState var isEditorFocused: Bool

    // Annotation state (#2458). The user's current text selection (UTF-16
    // offsets) drives the toolbar; `isComposingNote` presents the note popover.
    @State var selectionRange: Range<Int>?
    @State var isComposingNote = false
    @State var noteDraft = ""

    static let claimSourceHighlightId = "claim-source-highlight"

    /// Read-through resolution (#4318): `document` is a snapshot handed down by
    /// the shell; a workflow's mid-run page_content write lands via the change
    /// stream in the STORE (typically `childrenCache` — page children are never
    /// in `currentDocuments`). Resolving through `liveDocument(id:)` shows the
    /// fresh text without reselecting the page, and its `revision` read makes
    /// the splice re-render this pane.
    var pageDoc: Document? {
        guard let doc = document, doc.docType == .page else { return nil }
        return documentStore.liveDocument(id: doc.id) ?? doc
    }

    /// Decoded, display-ready page text. RTF source is resolved to plain text so
    /// the reader never shows raw `\'e1`/control-word escapes (#2317); everything
    /// downstream (edit draft, highlight ranges, claim matching) works off this
    /// same decoded string so offsets stay consistent.
    var pageContent: String {
        ArtifactRichTextCodec.plainText(pageDoc?.pageContent ?? "")
    }

    /// True while a running workflow targets this page (#4357). Reads the store's
    /// existing busy state (#4295) — the run's own target record — so the content
    /// view and the sidebar row agree about what is working.
    var isPageBusy: Bool {
        guard let id = pageDoc?.id else { return false }
        return documentStore.isDocumentBusy(id)
    }

    /// Work in progress on this page: a spinner plus what is happening. Never a
    /// raw status dump — the same quiet treatment the reader's page cards use.
    @ViewBuilder
    var workingState: some View {
        VStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)
            Text("Transcribing this page…")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityLabel("Transcribing this page")
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
                } else if isPageBusy {
                    // A run is writing THIS page (#4357): say so, rather than
                    // showing the same "No content" as an idle empty page. The
                    // text appears here the moment the write lands, via the
                    // read-through resolution above (#4318).
                    workingState
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
                    // A run writing this page shows progress in the bar too, so
                    // the signal survives once text starts arriving (#4357).
                    if isSaving || isPageBusy {
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
