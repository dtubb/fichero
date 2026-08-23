import SwiftUI

// MARK: - The library pane's floating head (Daniel, 2026-08-23)
//
// [library icon : view-mode picker] [breadcrumb] [split] — the same grammar
// as the reader, from the same shared components. The view-mode picker LEFT
// the window toolbar for this head; close and pin join when the pane grid
// gives them meaning here.

extension LibraryView {
    private var displayModeBinding: Binding<ViewDisplayMode> {
        Binding(
            get: { displayMode },
            set: { onChangeDisplayMode?($0) }
        )
    }

    /// Explicitly typed (the reader's type-checker rule applied here).
    private var librarySelector: PaneKindSelector<ViewDisplayMode> {
        PaneKindSelector(
            kindTitle: "Library",
            kindIcon: ToolbarSymbols.breadcrumbLibrary,
            lenses: availableDisplayModes,
            lensTitle: { (mode: ViewDisplayMode) in mode.label },
            lensIcon: { (mode: ViewDisplayMode) in mode.icon },
            lens: displayModeBinding
        )
    }

    var libraryPaneHead: some View {
        PaneHead<PaneKindSelector<ViewDisplayMode>, AnyView, EmptyView>(
            crumbs: libraryHeadCrumbs,
            onClose: nil,
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
            selector: { self.librarySelector },
            controls: { AnyView(self.libraryHeadControls) },
            tools: { EmptyView() }
        )
    }

    @ViewBuilder
    private var libraryHeadControls: some View {
        // No pin binding yet: pinning a library pane (to a folder / library)
        // has no plumbing, and a dead control is the menu lying.
        PaneChromeMenu(splitActions: nil, isPinned: nil)
    }

    private var libraryHeadCrumbs: [PaneCrumb] {
        var crumbs: [PaneCrumb] = []
        if let libraryId = LibraryManager.shared.currentLibraryId,
           let library = LibraryManager.shared.getLibrary(id: libraryId) {
            crumbs.append(PaneCrumb(
                id: "library-root",
                name: library.displayName,
                icon: ToolbarSymbols.breadcrumbLibrary,
                isNavigable: false
            ))
        }
        // `folderId` is the sidebar item id, which prefixes documents "doc:".
        let anchor = folderId.map { $0.hasPrefix("doc:") ? String($0.dropFirst(4)) : $0 }
        if let anchor {
            crumbs += libraryPathCrumbs(
                anchorId: anchor,
                resolve: { documentStore.resolveDocument($0) }
            ).map(PaneCrumb.init)
        }
        return crumbs
    }
}
