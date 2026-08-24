import SwiftUI

// MARK: - The preview pane's floating head (split for file_length)

extension ContentView {
    /// Explicitly typed (the reader's type-checker rule applied here).
    var previewSelector: PaneKindSelector<PreviewLens> {
        PaneKindSelector(
            kindTitle: "Preview",
            kindIcon: ToolbarSymbols.previewPane,
            lenses: PreviewLens.allCases,
            lensTitle: { (lens: PreviewLens) in lens.title },
            lensIcon: { (lens: PreviewLens) in lens.icon },
            lens: $previewLens
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
        return PaneHead<PaneKindSelector<PreviewLens>, EmptyView, EmptyView>(
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
                (documentStore.childrenCache[crumb.id] ?? []).map(PaneCrumb.init)
            },
            selector: { self.previewSelector },
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
    }
}
