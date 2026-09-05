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
        if isComparingArtifacts {
            // The compare lens outranks every other reading of the page: it is
            // the most specific thing the user asked for, and it is dismissed
            // from the same menu that started it.
            artifactCompareContent
        } else if let readerMarkdownText, readerRepresentation == nil, artifactLens == nil {
            // A Markdown document reads as MARKDOWN (Daniel, 2026-09-04),
            // through `MarkdownText` — the renderer the chat bubbles and the
            // preview canvas already use. Rendering it as HTML here would be a
            // second Markdown implementation, free to disagree with those two
            // about what a heading or a list looks like.
            ScrollView {
                MarkdownText(readerMarkdownText)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
            }
        } else if let readerCSVHTML, readerRepresentation == nil, artifactLens == nil {
            // A CSV document reads as a TABLE (Daniel, 2026-09-04). Only over
            // the document's own content: pointing the pane at a
            // representation or a named artifact is a request for THAT, and a
            // table drawn over it would be answering a different question.
            ReaderHTMLPane(html: readerCSVHTML)
        } else if let doc = effectiveDocument, doc.isWorkflowNode {
            // A workflow node cannot HAVE a transcript (Daniel, 2026-08-29):
            // the engine view's generic empty says one isn't available "yet",
            // which promises what cannot arrive. State the impossibility
            // natively, before any WebKit load, and offer the surface that
            // does show the node — the workflow editor.
            workflowNodeEmptyState(doc)
        } else if multiDocuments.count > 1 {
            // N pages of ONE parent ride the SAME WebKit transcript the
            // single-document reader uses — the surface's `?pages=` filter
            // tells the renderer which pages to assemble (2026-08-25). The
            // guard against `effectiveDocument`'s own mapping keeps the
            // filter honest: the ids must be children of the document the
            // surface is about to render. Mixed selections (across parents,
            // or non-pages) keep the native archival-order list.
            if let parentId = multiReaderCommonPageParent(multiDocuments),
               effectiveKGDocumentId == parentId {
                surfaceView(tab: .transcript, pageIds: multiDocuments.map(\.id))
            } else {
                MultiSelectionReaderView(documents: multiDocuments)
            }
        } else {
            surfaceView(tab: .transcript)
        }
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

    /// A workflow node's honest empty state (Daniel, 2026-08-29): "not
    /// possible", never "not yet". The button routes through the same reveal
    /// seam a sidebar click uses, which lands workflow mirrors in the editor
    /// (`routeWorkflowMirrorSelection`).
    private func workflowNodeEmptyState(_ doc: Document) -> some View {
        ContentUnavailableView {
            Label("Workflows Have No Transcript", systemImage: "arrow.triangle.branch")
        } description: {
            Text("\(DocumentTitle.displayName(for: doc)) is a workflow, not a document — there is no page text to read.")
        } actions: {
            Button("Open in Workflow Editor") {
                NotificationCenter.default.post(
                    name: .sidebarRevealDocument,
                    object: nil,
                    userInfo: ["documentId": doc.id]
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.textBackgroundColor))
        .accessibilityIdentifier("readerWorkflowNodeEmptyState")
    }

    private var readerEmptyState: some View {
        Text("No selection")
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
    }

    /// The in-reader find bar (#4338), hosted by the shared `PaneFilterBar`
    /// (top edge on Mac, bottom on touch — #4362): query field, "n of m"
    /// status, previous/next match, clear. The query and current match drive
    /// the shared WebKit surface's CSS-highlight finder; the surface reports
    /// the match count back.
    @ViewBuilder
    var readerFindBar: some View {
        Image(systemName: ToolbarSymbols.findField)
            .foregroundStyle(.secondary)
        TextField("Find in document", text: Binding(
            get: { searchState.query },
            set: { searchState.query = $0 }
        ))
        .textFieldStyle(.plain)
        .onSubmit { searchState.next() }
        .accessibilityIdentifier("readerFindField")

        if !searchState.query.isEmpty {
            Text(searchState.statusText)
                .font(.caption)
                .foregroundStyle(.secondary)
                .monospacedDigit()
            Button {
                searchState.previous()
            } label: {
                Image(systemName: ToolbarSymbols.findPrevious)
                    .readerIconTarget()
            }
            .buttonStyle(.plain)
            .disabled(searchState.matchCount == 0)
            .help("Previous match")
            .accessibilityLabel("Previous match")
            Button {
                searchState.next()
            } label: {
                Image(systemName: ToolbarSymbols.findNext)
                    .readerIconTarget()
            }
            .buttonStyle(.plain)
            .disabled(searchState.matchCount == 0)
            .help("Next match")
            .accessibilityLabel("Next match")
            Button {
                searchState.dismiss()
            } label: {
                Image(systemName: ToolbarSymbols.clearField)
                    .foregroundStyle(.secondary)
                    .readerIconTarget()
            }
            .buttonStyle(.plain)
            .help("Clear find")
            .accessibilityLabel("Clear find")
        }
        Spacer(minLength: 0)
    }

    /// The page children of the document this reader shows, live from the store.
    /// Page children live in `childrenCache` (the sidebar's cache) and, when the
    /// parent folder is the selection, in `currentDocuments` — read both so the
    /// per-page progress works from either surface (#4357).
    var readerPageChildren: [Document] {
        guard let doc = effectiveDocument else { return [] }
        let parentId = (doc.docType == .page ? doc.parentId : doc.id) ?? doc.id
        let cached = documentStore.childrenCache[parentId] ?? []
        let selected = documentStore.currentDocuments.filter { $0.parentId == parentId }
        var seen = Set<String>()
        return (cached + selected).filter { seen.insert($0.id).inserted }
    }

    /// Pages a run is writing right now — the run's target set via the store's
    /// existing busy state (#4295), not a second notion of "working" (#4357).
    var busyReaderPageNumbers: Set<Int> {
        ReaderPageProgress.busyPageNumbers(children: readerPageChildren) { pageId in
            documentStore.isDocumentBusy(pageId)
        }
    }

    /// Live text for the pages a run has touched, patched into the reader in
    /// place — never a reload (#4357).
    var readerPageContentPatches: [Int: String] {
        ReaderPageProgress.livePageContent(
            children: readerPageChildren,
            pages: ReaderPageProgress.trackedPages(
                alreadyTracked: trackedRunPages,
                busy: busyReaderPageNumbers
            )
        )
    }

    /// What this reader currently shows, for the highlight-layer precedence
    /// (#4355). `showsPageImage` is the Preview pane's business and is not yet
    /// plumbed across panes, so the geometry-mirroring arm stays dormant here.
    var readerVisibleSplit: ReaderVisibleSplit {
        ReaderVisibleSplit(
            showsTranscript: readerTab == .page,
            showsKnowledge: readerTab == .knowledge,
            isFinding: !searchState.query.isEmpty
        )
    }

    /// The claim to tint, or nil when another layer owns the surface. While find
    /// is running, the knowledge tint stands down: the same visual surface must
    /// not mean "match" and "claim" at once (#4355).
    var highlightedClaimId: String? {
        guard ReaderHighlightPrecedence.isVisible(.entityClaim, in: readerVisibleSplit) else {
            return nil
        }
        return kgFocusState.focusedClaimId ?? claimFocusState.selectedClaimId
    }

    /// The shared WebKit surface, driven by an explicit tab. The Page tab passes
    /// `.transcript` (the assembled multi-page transcript) and the Knowledge tab
    /// passes its viz sub-mode — one WKWebView, two readings of the same document.
    /// The document id the surface would render for the current
    /// `effectiveDocument` — a page maps to its parent, everything else to
    /// itself. Exposed so `pageTabContent` can verify a multi-page filter
    /// belongs to the document about to be rendered.
    var effectiveKGDocumentId: String? {
        guard let doc = effectiveDocument else { return nil }
        return Self.kgDocumentId(for: doc)
    }

    /// A page maps to its parent; a REGION node (a zone carrying
    /// `regionInParent` — a diary entry, a segment) maps to its parent too
    /// (Daniel, 2026-08-29): a region-scoped reader shows ALL regions of that
    /// view through the one WebKit renderer, so the view is OF the parent.
    static func kgDocumentId(for doc: Document) -> String {
        guard let parentId = doc.parentId else { return doc.id }
        return (doc.docType == .page || doc.regionInParent != nil) ? parentId : doc.id
    }

    @ViewBuilder
    func surfaceView(tab: KGSurfaceTab, pageIds: [String] = []) -> some View {
        if let doc = effectiveDocument,
           let libraryPath = apiClient.currentLibraryPath, !libraryPath.isEmpty {
            // A single selected REGION asks for the region's OWN id: the
            // engine re-anchors the view to the parent and lists the whole
            // cohort — same page, same output type — so one region selected
            // reads as ALL its sibling regions (Daniel, 2026-08-29). A
            // multi-selection (`pageIds`) anchors on the parent and filters.
            let kgDocId = (pageIds.isEmpty && doc.regionInParent != nil)
                ? doc.id
                : Self.kgDocumentId(for: doc)
            DocumentKGSurface(
                documentId: kgDocId,
                documentScope: doc.docType == .page ? .page : .folder,
                libraryPath: libraryPath,
                pageIds: pageIds,
                // The representation switcher applies to the PAGE reading of
                // the document; the knowledge sub-modes read the live graph.
                // The artifact lens outranks the representation switcher
                // (Daniel, 2026-08-30): the SAME WebKit renderer reads one
                // named artifact via the "artifact:<id>" channel — tables
                // parse, translations read as prose, split panes each hold
                // their own.
                representation: tab == .transcript
                    ? (artifactLens.map { "artifact:\($0.artifactId)" } ?? readerRepresentation)
                    : nil,
                selectedEntityId: kgFocusState.focusedEntityId,
                selectedClaimId: highlightedClaimId,
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
                document: doc,
                // In-reader find (#4338): 0-based select index for the JS side.
                searchQuery: searchState.query,
                searchSelectionIndex: searchState.currentIndex - 1,
                onSearchMatchCount: { count in searchState.recordMatches(count) },
                // Per-document work shown in place (#4357): the run's pages get
                // a spinner, and their text lands live.
                busyPageNumbers: busyReaderPageNumbers,
                pageContentPatches: readerPageContentPatches
            )
        } else {
            readerEmptyState
        }
    }
}
