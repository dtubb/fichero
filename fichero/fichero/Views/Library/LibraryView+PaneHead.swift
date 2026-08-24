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
            set: { mode in
                if isSecondarySplitPane {
                    // A split's secondary pane keeps its OWN mode (Daniel,
                    // 2026-08-23: choosing 3D in one must not flip both).
                    paneDisplayModeOverride = mode
                } else {
                    paneDisplayModeOverride = nil
                    onChangeDisplayMode?(mode)
                }
            }
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
            // The three sections the toolbar menu had (browse / dataset /
            // canvas), from the enum's own grouping so the menu cannot drift.
            lensSections: ViewDisplayMode.Group.allCases.compactMap { group in
                let modes = availableDisplayModes.filter { $0.group == group }
                return modes.isEmpty ? nil : (group.rawValue, modes)
            },
            lens: displayModeBinding
        )
    }

    var libraryPaneHead: some View {
        PaneHead<PaneKindSelector<ViewDisplayMode>, EmptyView, EmptyView>(
            crumbs: libraryHeadCrumbs,
            onClose: onClosePane,
            isPinned: isPanePinned,
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
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
    }

    private var libraryHeadCrumbs: [PaneCrumb] {
        var crumbs: [PaneCrumb] = []
        if let libraryId = LibraryManager.shared.currentLibraryId,
           let library = LibraryManager.shared.getLibrary(id: libraryId) {
            crumbs.append(PaneCrumb(
                id: "library-root",
                title: library.displayName,
                icon: "books.vertical.fill",
                isNavigable: false,
                tint: .accentColor
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
