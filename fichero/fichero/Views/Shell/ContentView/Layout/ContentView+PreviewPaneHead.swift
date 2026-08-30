import SwiftUI

// MARK: - The preview pane's floating head (split for file_length)
//
// Restructured 2026-08-29 (Daniel, Preview.app as the model):
//   • pages ‹ › (with an up-to-parent step) sit LEFT of the breadcrumb,
//     inside the identity capsule;
//   • region show/hide + the renditions MENU sit top-right by the
//     breadcrumb, the reader's transcript/translation menu grammar;
//   • the head's PENCIL toggle slides the markup row out UNDER the head —
//     annotation overlays Preview, not a separate mode.

extension ContentView {
    /// The canvas pane's head + chrome plumbing, in one place (also keeps
    /// ContentView+DetailLayout under its file-length budget):
    /// the floating head (Daniel, 2026-08-23), the head ↔ canvas chrome seam,
    /// the outline fetch that feeds the crumbs, the quiet bar's ⓘ, and the
    /// edit-lens ↔ Edits-facet sync (all Daniel, 2026-08-29).
    func previewHeadPlumbing(around content: some View) -> some View {
        content
            .environment(previewChrome)
            .safeAreaInset(edge: .top, spacing: 0) { previewPaneHead }
            // Mandate 1, consumer 1: the shown item's outline feeds the
            // head's crumb chain (entry → page → spread parents included).
            .task(id: detailDocument?.id) {
                if let id = detailDocument?.id {
                    await documentStore.loadOutline(for: id)
                }
            }
            // Quiet-bar info button: metadata lives in the inspector.
            .onReceive(
                NotificationCenter.default.publisher(for: .previewShowInfo)
            ) { _ in
                showInspectorSidebar.toggle()
            }
            // Multi-selection shows the stack — no pages/renditions to
            // serve, so a departing canvas's chrome must not linger.
            .onChange(of: browserSelection) { _, selection in
                if selection.count > 1 { previewChrome.reset() }
            }
            // Keep the head's lens honest when edit mode is entered from
            // the Inspector's Edits facet instead of the lens menu.
            .onChange(of: previewEditorTab) { _, tab in
                let lens: PreviewLens = (tab == .edits) ? .edit : .preview
                if previewLens != lens { previewLens = lens }
            }
    }

    /// Explicitly typed (the reader's type-checker rule applied here).
    var previewSelector: PaneKindSelector<PreviewLens> {
        PaneKindSelector(
            kindTitle: "Preview",
            kindIcon: ToolbarSymbols.previewPane,
            lenses: PreviewLens.allCases,
            lensTitle: { (lens: PreviewLens) in lens.title },
            lensIcon: { (lens: PreviewLens) in lens.icon },
            lens: previewLensBinding
        )
    }

    /// Picking Edit ENTERS edit mode (Daniel, 2026-08-29): the lens writes the
    /// same per-window key the Inspector's Edits facet and EditorView already
    /// share, so the head, the inspector and the canvas cannot disagree.
    var previewLensBinding: Binding<PreviewLens> {
        Binding(
            get: { previewLens },
            set: { lens in
                previewLens = lens
                previewEditorTab = (lens == .edit) ? .edits : .content
            }
        )
    }

    var previewPaneHead: some View {
        // The crumb names what the preview SHOWS — the image / spread /
        // page / region itself, never the folder it lives in (Daniel,
        // 2026-08-23). Same resolution the content branches use.
        let shown = CanvasDocumentPolicy.documentForCanvas(
            selectedDocumentIds: browserSelection,
            documents: selectedDocuments,
            detailDocument: detailDocument,
            inspectorDocument: inspectorDocument
        ) ?? detailDocument
        var crumbs: [PaneCrumb] = []
        if let doc = shown {
            let ancestry = libraryPathCrumbs(
                anchorId: doc.id,
                resolve: { documentStore.resolveDocument($0) }
            )
            crumbs = ancestry.isEmpty ? [PaneCrumb(doc)] : ancestry.map(PaneCrumb.init)
        }
        // The one-click return to the SPREAD a region/page-part came from
        // (Daniel, 2026-08-29: the crumb is orientation; this lives with the
        // paging controls). Present only when the shown document has a
        // navigable parent in its ancestry.
        let parentCrumb: PaneCrumb? = crumbs.count >= 2 ? crumbs[crumbs.count - 2] : nil
        // Breadcrumb honesty (Daniel, 2026-08-29): with N>1 items selected
        // the head must SAY so — the ancestry for context, then "N items" —
        // never present one document as if it were the whole selection.
        if browserSelection.count > 1 {
            if !crumbs.isEmpty { crumbs.removeLast() }
            crumbs.append(.multiSelection(count: browserSelection.count))
        }
        return PaneHead<PreviewHeadSelectorGroup, PreviewHeadLensControls, PreviewMarkupToolsRow>(
            crumbs: crumbs,
            onClose: { setPaneVisible(.canvas, false) },
            isPinned: Binding(
                get: { pinnedPreviewDocument != nil },
                set: { pin in pinnedPreviewDocument = pin ? shown : nil }
            ),
            onCrumb: { crumb in
                NotificationCenter.default.post(
                    name: .sidebarRevealDocument,
                    object: nil,
                    userInfo: ["documentId": crumb.id]
                )
            },
            crumbChildren: { crumb in
                (documentStore.outline(for: crumb.id)?.children
                    ?? documentStore.childrenCache[crumb.id]
                    ?? []).map(PaneCrumb.init)
            },
            crumbDragPayload: { crumb in
                paneCrumbDragPayload(crumb, store: documentStore, libraryId: windowState.libraryId)
            },
            selector: {
                PreviewHeadSelectorGroup(
                    selector: self.previewSelector,
                    chrome: self.previewChrome,
                    onUpToParent: parentCrumb.flatMap { (parent: PaneCrumb) -> (() -> Void)? in
                        guard parent.isNavigable, browserSelection.count <= 1 else { return nil }
                        return {
                            NotificationCenter.default.post(
                                name: .sidebarRevealDocument,
                                object: nil,
                                userInfo: ["documentId": parent.id]
                            )
                        }
                    }
                )
            },
            controls: { PreviewHeadLensControls(chrome: self.previewChrome) },
            tools: { PreviewMarkupToolsRow() },
            toolsIcon: "pencil.tip.crop.circle",
            toolsHelp: "markup row"
        )
    }
}
