import SwiftUI

// MARK: - ContentView Detail Layout Extension
// Agent: ViewBuilderAgent
// Responsibility: Detail-column chrome (tab strip/status/location bars), the
// widescreen canvas/reading panes, and the preview/inspector/detail views.
// Split out of ContentView+ViewBuilders.swift to keep each file under the
// file_length limit.

extension ContentView {
    @ViewBuilder
    var detailShellColumn: some View {
        VStack(spacing: 0) {
            // Xcode-style detail chrome (tab strip + location/status path bars)
            // is a regular-width affordance. At compact width (iPhone) it wastes
            // the tiny screen and doesn't fit, so it's hidden — the reader gets
            // the full height (#2811). macOS reports a regular/nil size class, so
            // the chrome always renders there.
            // The detail tab strip is RETIRED (Daniel, 2026-08-23): the
            // selected item reads from the top dynamic island, and "open in
            // new tab" returns on the real tab bar when that exists. Panes
            // carry their own PaneHead — no second chrome row above them.
            centerContent
            // NO window-wide status bar any more (Daniel #106-108,
            // 2026-08-09: "we want the status bar just on the library") —
            // the Finder-style path + status rows live in LibraryView's
            // bottom inset, scoped to that pane. See LibraryPathStatusBar.
        }
        .background(Color(platformColor: .textBackgroundColor))
        // Keep every library/preview/reader combination inside the detail
        // column bounds. Without this outer clip, inner split panes can still
        // paint under the shell sidebar or past the left window edge (#3336).
        .clipped()
        // Window split commands + workspace capture (Daniel, 2026-08-29).
        .environment(\.paneSplitCoordinator, paneSplitCoordinator)
    }

    // detailStatusPathBar is RETIRED (Daniel #106-108) — see the comment at
    // its old mount above. selectionStatusText remains in StateDisplay for
    // the toolbar/other readers.

    /// The document-canvas pane of the widescreen reading layout — a PDF page
    /// viewer when a PDF is active, otherwise the image/preview editor. Carries
    /// its own flexible width so it fills whatever the list/reading panes leave.
    /// Extracted so the canvas can be conditionally shown/hidden (#1448).
    @ViewBuilder
    func widescreenCanvasPane(splitKey: String = "canvas") -> some View {
        // Splittable (h/v) image / canvas viewer — #2276. The split key is
        // SLOT-scoped (2026-08-24): two slots hosting previews shared the
        // per-window "canvas" @SceneStorage, so splitting one split both.
        adaptiveSplittablePane(storageKey: splitKey) {
            // F3: the pin lives in the per-split HOST, not on ContentView, so
            // each SplittablePane sub-instance pins independently (mirrors
            // ReadingPaneView's own @State). The host is built INSIDE this
            // per-sub-pane closure, so left and right halves get distinct
            // @State — a shared ContentView @State pinned both at once.
            PreviewSplitPaneHost { pinnedPreviewDocument in
                // The head, the chrome seam, and their sync live in
                // ContentView+PreviewPaneHead.swift (2026-08-29 restructure).
                previewHeadPlumbing(
                    around: widescreenCanvasPaneContent(
                        pinnedPreviewDocument: pinnedPreviewDocument.wrappedValue
                    ),
                    pinnedPreviewDocument: pinnedPreviewDocument
                )
            }
        }
    }

    @ViewBuilder
    private func widescreenCanvasPaneContent(pinnedPreviewDocument: Document?) -> some View {
        let stackDocuments = previewStackDocuments(
            selection: browserSelection, in: selectedDocuments
        )
        // Pinned: frozen on the captured document, whatever the selection
        // does (Daniel, 2026-08-23: pin = pin to current view). The pinned
        // snapshot wins over the live selection (PreviewPanePin) — a pinned
        // pane does not follow selection; `live: nil` because the frozen pane
        // deliberately skips the stack/PDF renderings of the live set below.
        if let pinned = PreviewPanePin.effectiveDocument(
            pinned: pinnedPreviewDocument, live: nil
        ) {
            EditorView(
                document: pinned,
                showHeader: false,
                onPDFPageIndexChange: { _ in },
                onNavigateToDocument: { _ in },
                selectedDocumentIDs: []
            )
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        // #4705 increment 2: a selected workflow's canvas renders HERE, in
        // Source/Preview — the Library pane stays the navigator (`Nav`'s
        // `.workflow` case no longer takes it over). A pin still wins first
        // (checked above) — pinning freezes a pane on whatever it showed, and
        // a workflow selection must not steal that. `isSecondarySplitPane`
        // (`PaneList.secondaryLeafIDs()`) refuses a SECOND `WorkflowEditor`
        // mount: two editors bound to the same `editingWorkflow` would run
        // independent autosave tasks against one binding (a real write
        // race) — the split affordance already declines to offer a second
        // one (`PaneSurface.allowsSplit`), this is the belt-and-suspenders
        // render-time guarantee for however else a duplicate Preview leaf
        // might exist (a saved multi-pane workspace, for instance).
        } else if case .workflow(let selectedWorkflow) = viewMode, let selectedWorkflow {
            if isSecondarySplitPane {
                PaneEmptyStateView(
                    reason: "\"\(selectedWorkflow.name)\" is already open in the other pane."
                )
            } else {
                WorkflowEditor(
                    workflow: selectedWorkflow,
                    editingWorkflow: $editingWorkflow,
                    displayMode: .icon,
                    selectedDocumentIds: effectiveWorkflowRunSelection
                )
                .frame(maxWidth: .infinity)
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
            }
        // #4705 increment 4a: schedule/trigger/chain/batches/activity all
        // render their existing detail view here — the Library pane stays
        // the navigator (`Nav`'s router no longer takes it over for any of
        // these). None of these views holds a shared window-level binding
        // (`ScheduleDetailView`/`TriggerDetailView`/`ChainEditorView` take a
        // plain value param, `BatchRunView`/`ActivityDetailView` read their
        // own environment stores) — no split-race, so no `isSecondarySplitPane`
        // gate is needed here, unlike `.workflow` above.
        } else if Self.isNodeDetailOrRunHistoryMode(viewMode) {
            nodeDetailOrRunHistoryContent(for: viewMode)
        // Finder's stacked multi-selection preview (#95) — same gate as the
        // standard-layout preview pane.
        } else if stackDocuments.count > 1 {
            MultiSelectionPreviewStack(
                documents: stackDocuments,
                frontDocumentId: detailDocument?.id
            )
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
                .frame(maxWidth: .infinity)
        } else if let pdfDocumentId = detailPDFDocumentId, previewLens == .preview {
            PDFPageWithToolbar(
                documentId: pdfDocumentId,
                pageIndex: selectedPageIndex,
                onPageIndexChange: { index in
                    guard documentScrollSync.beginDriving(.pdf) else { return }
                    syncGridSelectionToPDFPage(index: index)
                },
                documentTitle: previewDocument?.name,
                onClose: { setPaneVisible(.canvas, false) },
                // Geometry lives on the PAGE child, not the parent PDF this
                // pane renders from (#4418 follow-up).
                geometryDocumentId: pageGeometryDocumentId
            )
            .frame(minWidth: ContentView.pdfCanvasMinWidth, maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        } else {
            // #4834: `previewDocument`, not `detailDocument` directly — a
            // knowledge-surface reveal must reach the canvas the same way
            // it reaches the PDF branch above (`detailPDFDocumentId`).
            let canvasDocument = CanvasDocumentPolicy.documentForCanvas(
                selectedDocumentIds: browserSelection,
                documents: selectedDocuments,
                detailDocument: previewDocument,
                inspectorDocument: inspectorDocument
            )
            EditorView(
                document: canvasDocument,
                showHeader: false,
                onPDFPageIndexChange: { index in
                    syncGridSelectionToPDFPage(index: index)
                },
                onNavigateToDocument: { docId in
                    selectDocument(withId: docId)
                },
                selectedDocumentIDs: browserSelection
            )
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        }
    }

    /// Whether `mode` is one of the five node-detail/run-history view modes
    /// `nodeDetailOrRunHistoryContent(for:)` renders (#4850 lint delivery —
    /// extracted so `widescreenCanvasPaneContent` fits SwiftLint's
    /// `function_body_length` error threshold; no behavior change, just a
    /// pure predicate over the SAME five `case` matches that used to be
    /// chained `else if` branches inline).
    private static func isNodeDetailOrRunHistoryMode(_ mode: AppViewMode) -> Bool {
        switch mode {
        case .chain, .batches, .schedule, .trigger, .activity: return true
        default: return false
        }
    }

    /// #4705 increment 4a's schedule/trigger/chain/batches/activity block —
    /// dispatches to the two extracted halves (#4850 lint delivery, no
    /// behavior change): `nodeDetailContent` (chain/batches/schedule/
    /// trigger) and `runHistoryContent` (activity). Split in two, not one,
    /// so neither trips SwiftLint's `function_body_length` WARNING
    /// threshold either (50 lines) — a single combined function fixed the
    /// ERROR but still warned.
    @ViewBuilder
    private func nodeDetailOrRunHistoryContent(for mode: AppViewMode) -> some View {
        if case .activity = mode {
            runHistoryContent(for: mode)
        } else {
            nodeDetailContent(for: mode)
        }
    }

    /// The chain/batches/schedule/trigger node-detail views. Each renders
    /// its existing detail view here; the Library pane stays the
    /// navigator. None of these views holds a shared window-level binding,
    /// so no `isSecondarySplitPane` gate is needed here, unlike `.workflow`
    /// in the caller.
    @ViewBuilder
    private func nodeDetailContent(for mode: AppViewMode) -> some View {
        if case .chain(let selectedChain) = mode {
            Group {
                if let selectedChain {
                    ChainEditorView(chain: selectedChain)
                } else {
                    // Relocated from the old Library-pane takeover, not
                    // deleted — still an honest "nothing to edit yet" state.
                    ContentUnavailableView(
                        "Create Chain",
                        systemImage: "link.badge.plus",
                        description: Text("Chain creation view")
                    )
                }
            }
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        } else if case .batches = mode {
            // Batch-mode GUI (#3536): run a workflow across many folders
            // separately — one run per folder, each tracked in Activity.
            BatchRunView()
                .frame(maxWidth: .infinity)
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        } else if case .schedule(let selectedSchedule) = mode {
            Group {
                if let selectedSchedule {
                    ScheduleDetailView(schedule: selectedSchedule)
                } else {
                    ScheduleEditorView(existingSchedule: nil)
                }
            }
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        } else if case .trigger(let selectedTrigger) = mode {
            Group {
                if let selectedTrigger {
                    TriggerDetailView(trigger: selectedTrigger)
                } else {
                    TriggerEditorView(existingTrigger: nil)
                }
            }
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        }
    }

    /// The activity/run-history detail view.
    @ViewBuilder
    private func runHistoryContent(for mode: AppViewMode) -> some View {
        if case .activity(let selectedRun) = mode {
            Group {
                if let selectedRun {
                    // The SAME component the compact flow and
                    // `ActivityDetailWindow.swift` already trust — replaces
                    // the deleted `ActivityWindowLauncherView`'s separate
                    // window.
                    ActivityDetailView(selectedRun: selectedRun)
                } else {
                    PaneEmptyStateView(reason: "Select a run in the sidebar to see its details.")
                }
            }
            .frame(maxWidth: .infinity)
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview })
        }
    }

    /// The reading / WebKit "Knowledge" pane of the widescreen layout.
    /// Extracted so it can be conditionally shown/hidden per-window (#1448).
    @ViewBuilder
    func widescreenReadingPane(splitKey: String = "reading") -> some View {
        widescreenReadingPaneBody(readingSplitKey: splitKey)
    }

    /// What the Reader shows: the selected document, or — when nothing is
    /// selected — the FOLDER that is open.
    ///
    /// With no selection the Reader used to show nothing at all (Daniel,
    /// 2026-08-28: "if only one item is selected it should show the entire
    /// folder, or no items as well; right now it shows nothing"). The engine
    /// already assembles every child page's content into one transcript for a
    /// container, which is exactly what a folder-level read wants, so the
    /// fallback costs no new backend work. It also makes the head's artifact
    /// lens reachable for the folder — a folder-level translation is
    /// selectable the same way a page's is.
    var readerDocument: Document? {
        // #4834: a knowledge-surface reveal wins first — same tier as
        // `detailDocument` below, just checked before it, so a reveal is
        // never shadowed by whatever the browser last had selected.
        if let sourceRevealDocument { return sourceRevealDocument }
        if let detailDocument { return detailDocument }
        if case .library(let folder) = viewMode { return folder }
        return nil
    }

    /// What Preview shows — the reveal-aware sibling of `readerDocument`
    /// (#4834). `widescreenCanvasPaneContent`'s PDF/canvas branches read
    /// THIS, not `detailDocument` directly, so a knowledge-surface reveal
    /// reaches Preview the same way it reaches the Reader. `inspectorDocument`
    /// (`ContentView+StateSelection.swift`) deliberately never reads this —
    /// that is what keeps a reveal from flipping the Inspector off whatever
    /// entity/claim it has focused.
    var previewDocument: Document? {
        sourceRevealDocument ?? detailDocument
    }

    @ViewBuilder
    private func widescreenReadingPaneBody(readingSplitKey: String) -> some View {
        // Compute the page count ONCE (#3866): reading `pdfDocPages` twice here
        // (isEmpty + count) recomputed a filter+sort per read — 2x O(n log n) per
        // render. The pane needs only the count, so use the sort-free accessor.
        let pageCount = pdfDocPageCount
        // Multi-selection is stated honestly (Daniel 2026-08-11: three items
        // selected, the preview showed the 3-item stack, the inspector said
        // "3 Items Selected" — and the reader silently showed ONE page's
        // transcript). Same gate as both of those panes. Rendering content
        // for ALL selected items is the pane-rebuild enhancement; until then
        // the reader must not present one item's text as the selection's.
        let readerStack = previewStackDocuments(
            selection: browserSelection, in: selectedDocuments
        )
        // Each SplittablePane instance renders ReadingPaneView independently,
        // giving left and right split panes their own @State (including pin).
        //
        // AnyView — LOAD-BEARING (#4331 family, Daniel's crash 2026-08-11
        // evening): EXC_BAD_ACCESS in objc_retain while initializeWithCopy
        // COPIED the composed reading-pane value through three
        // ExclusiveGesture wrappers (SidebarLayout:242). The multi-select
        // _ConditionalContent grew the value past what the copy machinery
        // survives; erasure at the case boundary caps it, same as the root
        // layout and window root.
        adaptiveSplittablePane(storageKey: readingSplitKey) {
            // ONE pane for both selection widths (2026-08-25): the multi view
            // used to replace ReadingPaneView wholesale, so a 3-item
            // selection erased the head, lens selector and crumbs. Now the
            // Page lens renders the multi list INSIDE the pane's chrome.
            // AnyView stays load-bearing (#4331).
            AnyView(ReadingPaneView(
                liveDocument: readerDocument,
                // NOT gated on the PDF canvas (Daniel, 2026-09-04): an image
                // page never uses that canvas, so the reader was handed no
                // active page and never scrolled to a search hit.
                liveActivePageNumber: readerActivePageNumber,
                // Scroll-by-id (#reader-page-id): lands on the exact page even
                // when its top-level `sequence` is null (manifest-imported image
                // pages), which the ordinal above cannot.
                liveActivePageId: readerActivePageId,
                livePageCount: pageCount == 0 ? nil : pageCount,
                scrollSync: documentScrollSync,
                onPageSelected: { index in syncGridSelectionToPDFPage(index: index) },
                onClose: { setPaneVisible(.reading, false) },
                multiDocuments: readerStack,
                // The active library-search terms, so the reader lights up
                // where the selected result matched (Daniel, 2026-09-01).
                searchHighlightQuery: chromeUX.readerFindQuery,
                // #4705 "4b-1" (#4803): the Reader now consults the matrix
                // instead of trusting whatever `readerDocument` still holds
                // from the last document selection — the fix for the
                // stale-Reader bug. Same no-`entitySelection`-passed style
                // as this file's other two `PaneContentPlan.plan(for:)`
                // call sites (the preview/inspector empty-reason reads
                // below).
                readerCell: PaneContentPlan.plan(for: viewMode).reader,
                // #4705 "4b-2" (#4741): WHICH schedule/trigger/run, computed
                // from the SAME `viewMode` as `readerCell` above so the two
                // can never disagree — and the kind-specific "nothing
                // selected" sentence for when there isn't one.
                readerSubject: PaneContentPlan.ReaderSubject.from(viewMode),
                readerRunHistoryEmptyReason: viewMode.runHistoryEmptyReason
            ))
        }
        // Native focus rings OFF in this pane: macOS 14+ makes scroll views
        // keyboard-focusable and rings them natively, which painted a
        // persistent blue edge above the reader toolbar. Panes draw no focus
        // ring of their own either (ruling 2026-08-31).
        .focusEffectDisabled()
        .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .reading; paneFocusHint = .reading })
    }

    // `adaptiveSplittablePane` is internal (not private) because it is also
    // called from ContentView+SidebarLayout.swift's `centerContentRouting`
    // (the widescreen library-pane split) — `private` is file-scoped.
    @ViewBuilder
    func adaptiveSplittablePane<Content: View>(
        storageKey: String,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        if shouldUseSplittablePane {
            SplittablePane(storageKey: storageKey) {
                content()
            }
        } else {
            content()
        }
    }

    // MARK: - Preview View

    /// Preview/editor view for selected item
    @ViewBuilder
    var previewView: some View {
        switch viewMode {
        case .library:
            // Stable .id so EditorView keeps its mount across the
            // first detailDocument nil → some-doc transition. Without
            // a fixed id, SwiftUI's structural-identity pass treats
            // the EditorView differently when its document arg flips,
            // causing the LazyVGrid sibling to re-layout / first-click
            // flash (#788).
            VStack(spacing: 0) {
                let previewDocument = CanvasDocumentPolicy.documentForCanvas(
                    selectedDocumentIds: browserSelection,
                    documents: selectedDocuments,
                    detailDocument: detailDocument,
                    inspectorDocument: inspectorDocument
                )
                let stackDocuments = previewStackDocuments(
                    selection: browserSelection, in: selectedDocuments
                )
                if stackDocuments.count > 1 {
                    // Finder's stacked multi-selection preview (#95): the fan
                    // + count, not a silent preview of only the primary.
                    MultiSelectionPreviewStack(
                        documents: stackDocuments,
                        frontDocumentId: detailDocument?.id
                    )
                } else if let pdfDocumentId = detailPDFDocumentId, previewLens == .preview {
                    PDFReadingView(
                        document: pageFocusDocument ?? detailDocument,
                        pdfDocumentId: pdfDocumentId,
                        pageIndex: selectedPageIndex,
                        contentWidth: $pageContentPaneWidth,
                        onPageIndexChange: { index in
                            guard documentScrollSync.beginDriving(.pdf) else { return }
                            syncGridSelectionToPDFPage(index: index)
                        }
                    )
                    .id("reader.pdf")
                    .background(
                        // Two/three-finger trackpad swipe → previous/next sibling
                        // (#593). Lives behind the reader so it sees the swipe
                        // without intercepting clicks/scrolls.
                        SwipeSiblingNavigator(
                            onNavigatePrevious: navigateSiblingPrevious,
                            onNavigateNext: navigateSiblingNext
                        )
                    )
                } else {
                    EditorView(
                        document: previewDocument,
                        onPDFPageIndexChange: { index in
                            syncGridSelectionToPDFPage(index: index)
                        }
                    )
                    .id("editor.library")
                    .background(
                        // Two/three-finger trackpad swipe → previous/next sibling
                        // (#593). Lives behind the editor so it sees the swipe
                        // without intercepting clicks/scrolls.
                        SwipeSiblingNavigator(
                            onNavigatePrevious: navigateSiblingPrevious,
                            onNavigateNext: navigateSiblingNext
                        )
                    )
                }
            }

        case .chat, .comparison, .workflow, .chain, .batches,
             .automation, .schedule, .trigger, .activity:
            // #4525 (V3): never a silent EmptyView — the pane stays mounted
            // and says why, from the ONE decided matrix. While the mode's
            // surface still renders in the center takeover (the remaining
            // #4525 step), a `.content` cell here falls back to naming where
            // the surface currently lives rather than showing a blank.
            PaneEmptyStateView(
                reason: PaneContentPlan.plan(for: viewMode).preview.emptyReason
                    ?? "This view is shown in the main area."
            )
        }
    }

    // MARK: - Inspector View

    /// Inspector/info sidebar view (rendered inside .inspector panel)
    @ViewBuilder
    var inspectorView: some View {
        switch viewMode {
        case .library:
            // Multi-selection interim (#146/#147, Daniel: 'this will be
            // tricky for document inspector. perhaps for now it just
            // disables?'): a clear N-items state instead of silently
            // inspecting only the primary. The aggregate views (all entities
            // across the selection; artifacts grouped by source) are the
            // designed follow-up — task #35.
            if browserSelection.count > 1 {
                ContentUnavailableView(
                    "\(browserSelection.count) Items Selected",
                    systemImage: "square.on.square",
                    description: Text(
                        "Select a single item to inspect it. Multi-item editing is coming."
                    )
                )
            } else {
            DocumentInspector(
                document: inspectorDocument,
                onNavigateToSource: { sourceDocId in
                    Task { @MainActor in
                        await navigateToSourcePage(sourceDocId)
                    }
                }
            )
            .environment(documentStore.documentService)
            .environment(artifactService)
            .environment(entityService)
            .environment(kgCurationService)
            .environment(documentStore)
            .environment(artifactStore)
            .environment(entityStore)
            .environment(claimStore)

            }

        case .chat, .comparison:
            ChatInspector(
                selectedDocuments: $chatSelectedDocuments,
                suggestedDocumentIDs: ChatScopeBuilder.currentScopeDocumentIds(
                    browserSelection: browserSelection,
                    currentDocuments: documentStore.currentDocuments,
                    detailDocument: detailDocument
                ),
                onAddSuggestedDocuments: {
                    let scopedIds = ChatScopeBuilder.currentScopeDocumentIds(
                        browserSelection: browserSelection,
                        currentDocuments: documentStore.currentDocuments,
                        detailDocument: detailDocument
                    )
                    chatSelectedDocuments = chatSelectedDocuments.union(scopedIds)
                }
            )

        case .workflow:
            WorkflowInspector(
                workflow: $editingWorkflow,
                onAddNode: { tool, position in
                    addNodeFromTool(tool, at: position)
                }
            )

        case .chain, .batches, .automation, .schedule, .trigger, .activity:
            // #4525: the honest per-mode empty from the ONE decided matrix,
            // replacing both the generic "Select an item to inspect." stub and
            // the chain's WorkflowInspector bound to whatever workflow was
            // last edited (a stale surface — the pane-audit's 💀 cell).
            PaneEmptyStateView(
                reason: PaneContentPlan.plan(for: viewMode).inspector.emptyReason
                    ?? "Select an item to inspect.",
                systemImage: "info.circle"
            )
        }
    }

    // MARK: - Detail View (Right Column)

    @ViewBuilder
    var detailView: some View {
        inspectorView
            // Focus tracking without .focusable() — avoids swallowing first click
            .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .inspector; paneFocusHint = .inspector })
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(.bar)
    }
}

// MARK: - Preview pane pin resolution (F3)

/// Pure pin-decision for the preview pane, extracted so the F3 behaviour is
/// unit-testable without a running view. A pane resolves to its pinned snapshot
/// when one exists, otherwise the live selection — so two `PreviewSplitPaneHost`
/// instances holding DIFFERENT pin state resolve to different documents from the
/// same live selection, which is exactly independent per-split pinning.
enum PreviewPanePin {
    /// The document the pane shows: the pinned snapshot wins over the live
    /// selection (a pinned pane does not follow selection).
    static func effectiveDocument(pinned: Document?, live: Document?) -> Document? {
        pinned ?? live
    }

    /// Whether the pane is pinned — a snapshot has been captured.
    static func isPinned(pinned: Document?) -> Bool {
        pinned != nil
    }
}

// MARK: - Preview split-pane host (F3)

/// Per-split-pane owner of the preview pin. Built INSIDE the SplittablePane
/// per-sub-pane `content()` closure, so each sub-instance gets its own
/// `@State` — exactly how `ReadingPaneView` owns `isPinned`/`pinnedDocument`.
/// Splitting the preview and pinning one half no longer pins both, because the
/// pin no longer lives on the single ContentView above the split boundary.
///
/// The pin freezes on whatever document was shown at pin time: the head's
/// binding setter captures the current `shown` document into this @State, and
/// the content reads it in place of the live selection (see
/// `widescreenCanvasPaneContent` / `previewPaneHead`).
private struct PreviewSplitPaneHost<Content: View>: View {
    @State private var pinnedPreviewDocument: Document?
    let content: (Binding<Document?>) -> Content

    var body: some View {
        content($pinnedPreviewDocument)
    }
}

// MARK: - Previews

// Same shape as `LibrarySplitPaneHost`: no chrome of its own, it just holds the pinned
// document for the preview half. The preview shows the binding round-tripping.
#Preview("Preview split pane host — the pinned document it carries") {
    PreviewSplitPaneHost { pinned in
        VStack(spacing: 8) {
            Text(pinned.wrappedValue == nil ? "No pinned document" : "Document pinned")
                .font(.callout)
            Button("Clear pin") { pinned.wrappedValue = nil }
        }
        .padding()
        .frame(width: 280, height: 120)
    }
}
