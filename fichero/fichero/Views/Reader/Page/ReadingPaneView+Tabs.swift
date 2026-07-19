import SwiftUI

// Reader tab routing (Page/Knowledge/Notes), the Page + Notes tab content, and
// the shared WebKit surface. Split out of ReadingPaneView to keep the type body
// under the SwiftLint threshold.
extension ReadingPaneView {
    /// Routes the selected reader tab to its content, native chrome over the
    /// WebKit/native surfaces (reader IA fold). Page = read the source (image /
    /// PDF with loupe #2419 / transcript); Knowledge = the WebKit KG surface;
    /// Notes = the reading layer (highlights/notes/bookmarks).
    @ViewBuilder
    var readerTabContent: some View {
        switch readerTab {
        case .page:
            pageTabContent
        case .knowledge:
            knowledgeTabContent
        case .notes:
            notesTabContent
        }
    }

    /// Page tab — the REAL multi-page WebKit transcript (#3765).
    ///
    /// This is the whole point of the Reader. The engine assembles the
    /// `page_content` of EVERY child page, in sequence, into one transcript
    /// (`views.py:37-49`), serves it into `document_view.html`, and
    /// `DocumentKGSurface` renders it in the shared WKWebView with per-page
    /// anchors driving scroll↔page sync (#3226). That capability was UNREACHABLE:
    /// the Knowledge surface excluded `.transcript`, and what the Reader called
    /// "Transcript" was a different, single-page NATIVE pane — the name lied.
    ///
    /// The source is NOT here and never will be: source is always Preview
    /// (2026-07-14, #3765 Q4). Reading the transcript beside the page is
    /// TWO PANES — Reader + Preview — not an embedded source view.
    @ViewBuilder
    private var pageTabContent: some View {
        surfaceView(tab: .transcript)
    }

    /// Notes tab — the human reading layer. A sub-mode toggle (#3513) switches
    /// between anchored **Marks** (highlights / notes / bookmarks via the shared
    /// `AnnotationsInspectorPane`) and free-text document **Notes** (NoteStore
    /// via `DocumentNotesTab`), so both loose notes and page-anchored marks live
    /// under one tab.
    @ViewBuilder
    private var notesTabContent: some View {
        if let doc = effectiveDocument {
            VStack(spacing: 0) {
                Picker("Notes mode", selection: notesModeBinding) {
                    ForEach(ReaderNotesMode.allCases) { mode in
                        Label(mode.title, systemImage: mode.icon)
                            .help(mode.help)
                            .tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .labelStyle(.titleAndIcon)
                .fixedSize()
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .accessibilityIdentifier("readerNotesMode")

                Divider()

                switch notesMode {
                case .annotations:
                    AnnotationsInspectorPane(
                        document: doc,
                        annotations: annotationStore.annotations,
                        focused: focusedAnnotation
                    )
                    .task(id: doc.id) {
                        await annotationStore.loadAnnotations(for: annotationScope(for: doc), force: true)
                    }
                case .notes:
                    DocumentNotesTab(document: doc)
                }
            }
        } else {
            readerEmptyState
        }
    }

    private func annotationScope(for doc: Document) -> AnnotationScope {
        switch doc.docType {
        case .folder: return .folder(doc.id)
        case .page: return .page(doc.id)
        default: return .document(doc.id)
        }
    }

    private var readerEmptyState: some View {
        Text("No selection")
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
    }

    /// The shared WebKit surface, driven by an explicit tab. The Page tab passes
    /// `.transcript` (the assembled multi-page transcript) and the Knowledge tab
    /// passes its viz sub-mode — one WKWebView, two readings of the same document.
    @ViewBuilder
    func surfaceView(tab: KGSurfaceTab) -> some View {
        if let doc = effectiveDocument,
           let libraryPath = apiClient.currentLibraryPath, !libraryPath.isEmpty {
            let kgDocId = (doc.docType == .page && doc.parentId != nil) ? doc.parentId! : doc.id
            DocumentKGSurface(
                documentId: kgDocId,
                documentScope: doc.docType == .page ? .page : .folder,
                libraryPath: libraryPath,
                selectedEntityId: kgFocusState.focusedEntityId,
                selectedClaimId: kgFocusState.focusedClaimId ?? claimFocusState.selectedClaimId,
                activePageNumber: effectivePageNumber,
                pageCount: effectivePageCount,
                onPageSelected: isPinned ? { _ in } : onPageSelected,
                scrollSync: scrollSync,
                zoom: webZoom,
                externalActiveTab: tab,
                // Only the Knowledge tab owns the sub-mode. A tab change published
                // while the transcript is showing must not silently rewrite it.
                onTabSelected: { newTab in
                    if tab != .transcript { activeTab = newTab }
                },
                document: doc
            )
        } else {
            readerEmptyState
        }
    }
}
