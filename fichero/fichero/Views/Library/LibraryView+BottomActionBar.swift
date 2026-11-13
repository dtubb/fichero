import FicheroAPIClient
import OSLog
import SwiftUI
// `UTType` came free while this lived in LibraryView.swift; a split file
// inherits symbols, not imports (#4353).
import UniformTypeIdentifiers

// The library's bottom action bar (#2313).
//
// Already its own extension with its own MARK and its own issue — moved to
// its own FILE for `file_length`, which #4353's strict tier treats as an
// error, not a warning. Splitting rather than shaving leaves real headroom:
// trimming to just under the limit would have been spent by the next edit.

// MARK: - Bottom Action Bar (#2313)
extension LibraryView {
    private var bottomBarLogger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "LibraryView.BottomBar")
    }

    /// Minimum hit-target side for each bottom-bar button. Follows the shared
    /// MiniToolbar metric policy: 28pt on the Mac (compact Finder bar) but 44pt
    /// on touch platforms so iPhone/iPad targets are comfortably tappable (#2474).
    private var bottomBarTouchTarget: CGFloat {
        MiniToolbar<EmptyView, EmptyView>.touchTargetSide
    }

    /// Height of the bottom action bar. Matches the shared mini-toolbar policy
    /// so library, sidebar, reader, preview, and inspector strips line up.
    private var bottomBarHeight: CGFloat {
        MiniToolbar<EmptyView, EmptyView>.standardHeight
    }

    /// Finder/Xcode-style bottom toolbar acting on the current library selection.
    ///
    /// Rewrapped on the shared `AdaptiveMiniToolbarRow` (#3057, parent #2670) so
    /// the bar no longer "extends and is weird" in a narrow pane: essential verbs
    /// stay inline, secondary verbs collapse into a trailing `…` menu when they
    /// don't fit (macOS) or on compact width (iPhone). Every action / `.help` /
    /// `.accessibilityLabel` is unchanged — iterate, never replace.
    /// Internal, not private: `bottomInsetContent` mounts this from
    /// LibraryView.swift, and `private` is FILE-scoped (#4353 split).
    var libraryBottomActionBar: some View {
        VStack(spacing: 0) {
            Divider()

            // Flat on macOS like Xcode's bars, the Liquid Glass island on touch (#2550,
            // `panes.chrome.bars-flush-on-mac`).
            // AnyView is load-bearing (#4331): the bar's four-slot toolbar row is the deepest generic type under
            // LibraryView.bottomInsetContent; on the iPad's 1MB main stack its metadata walk overflowed at launch (2026-11-12).
            AnyView(AdaptiveMiniToolbarRow {
                essentialBarButtons
            } secondary: {
                secondaryBarButtons
                // The sort/filter/metadata cluster folded in (Daniel,
                // 2026-08-23: one bottom mini toolbar, not stacked rows).
                libraryMiniToolbar
            } condensed: {
                // The rung between "everything inline" and "everything in
                // the ellipsis" (Daniel, 2026-08-31: "the ellipsis is too
                // greedy"). The same controls, wearing icons instead of
                // words — the bar buys back the width the two text-bearing
                // controls cost before it hides anything at all.
                condensedBarButtons
                libraryMiniToolbar(condensed: true)
            } overflowMenu: {
                // The sort/filter cluster survives narrow widths here
                // (Daniel, 2026-08-23: "we want them there"). The
                // metadata control used to VANISH at narrow widths —
                // its popover cannot live in a menu — so it now has a
                // submenu coat over the same binding (Daniel,
                // 2026-08-29: "loses some of the filter options when
                // it's too narrow").
                Divider()
                // LABELLED coats (Daniel, 2026-08-31): these rendered as
                // bare `⇅` chevron rows here, because the bar's icon-only
                // Menu label carries into a menu as a submenu with no name
                // at all. A menu row has room for a word and needs one.
                // The Show kinds are in the Filter field's menu now (`panes.chrome.one-filter-pattern`).
                if Self.barShowsSort(displayMode) { librarySortMenu(iconOnly: false) }
                LibraryRowAttributesMenu(raw: $rowAttributesRaw, contentLines: $rowContentLinesRaw)
                // Mode clusters reachable at narrow widths too (the gap
                // the consolidation design named): dataset facets and the
                // canvas channels as titled submenus.
                if displayMode.group == .dataset {
                    Divider()
                    DatasetFilterClusterMenu(store: datasetStore, documentStore: documentStore)
                }
                if displayMode.group == .canvas {
                    Divider()
                    CanvasControlStripMenu()
                }
            })
            .padding(.horizontal, 10)
            .frame(height: bottomBarHeight)
            // ONE control size for the whole bar (Daniel, 2026-08-24:
            // the +/− size is the right one; the sort/metadata cluster
            // rendered .regular). Environment value — every child
            // inherits; the per-button repeats are deleted.
            .controlSize(.small)
            .paneBarSurface()
        }
        // The ONE picker presenter for every import affordance in this view
        // (#4449) — the bottom-bar button below AND the folder contextual
        // menu (`LibraryView+ContextMenu.swift`) both flip `showingFileImporter`
        // after stating their target in `fileImportTargetFolderId`.
        .fileImporter(
            isPresented: $showingFileImporter,
            allowedContentTypes: [.item],
            allowsMultipleSelection: true,
            onCompletion: handleFileImport
        )
        // Sits beside the picker it reports on, so the alert and the one
        // handler that can populate it stay together (#3276).
        .alert(
            "Import Incomplete",
            isPresented: Binding(
                get: { importErrorMessage != nil },
                set: { if !$0 { importErrorMessage = nil } }
            )
        ) {
            Button("OK") { importErrorMessage = nil }
        } message: {
            Text(importErrorMessage ?? "")
        }
    }

    /// #4856: ONE add control, content-aware — a folder in Documents, an
    /// entity in Entities, a claim in Claims. Calls the SAME create paths
    /// the content's own former "New Entity"/"New Claim" button called
    /// (`kgContentAddRequested`, read by whichever `EntitiesLibraryContent`/
    /// `ClaimsLibraryContent` is mounted); it does not write a new one.
    private var addButtonLabel: String {
        switch effectiveContentKind {
        case .documents: return "New Folder"
        case .entities: return "New Entity"
        case .claims: return "New Claim"
        }
    }

    private var addButtonHelp: String {
        switch effectiveContentKind {
        case .documents: return "Create a new folder"
        case .entities: return "Create an entity by hand"
        case .claims: return "Assert a claim by hand"
        }
    }

    private func performAdd() {
        switch effectiveContentKind {
        case .documents: handleCreateNewFolder()
        case .entities, .claims: kgContentAddRequested = true
        }
    }

    private var addButtonAccessibilityIdentifier: String {
        switch effectiveContentKind {
        case .documents: return "library.newFolder"
        case .entities: return "kg.entity.new"
        case .claims: return "kg.claim.new"
        }
    }

    /// Essential verbs — always inline (#3057): the add control, Delete, Import.
    /// The trailing Spacer keeps them left-aligned with the secondary/overflow on
    /// the right, preserving the bar's existing Finder-style layout.
    @ViewBuilder
    private var essentialBarButtons: some View {
        // #4856's own open question, not decided here: whether Import (and
        // Delete/Export/Run-Workflow's existing content-aware `.disabled`
        // rules below) should HIDE rather than grey for a KG content kind
        // they don't apply to — left exactly as they behave today.
        // + adds: New Folder and Import Files… (the separate import button is gone, `panes.chrome.one-filter-pattern`).
        Group {
            if effectiveContentKind == .documents {
                Menu {
                    Button("New Folder", systemImage: "folder.badge.plus") { performAdd() }
                    Button("Import Files…", systemImage: "square.and.arrow.down") { openImportPicker() }
                } label: {
                    Image(systemName: "plus").accessibilityLabel("Add")
                }
                .menuStyle(.button)
                .menuIndicator(.hidden)
            } else {
                Button { performAdd() } label: {
                    Image(systemName: "plus").accessibilityLabel(addButtonLabel)
                }
            }
        }
        .paneBarButtonStyle()
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help(addButtonHelp)
        .accessibilityIdentifier(addButtonAccessibilityIdentifier)

        Button {
            promptDeleteSelected()
        } label: {
            Image(systemName: "trash")
                .accessibilityLabel("Move to Trash")
        }
        .paneBarButtonStyle()
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Move the selection to the Trash")
        .disabled(isShowingEntitiesCollection || selection.isEmpty)

        Spacer()
    }

    /// Secondary verbs — inline on Mac when they fit, else the `…` menu; menu-only
    /// on compact (#3057): the KG content filter (Entities/Claims), the
    /// entity filter (list mode), Export BibTeX, Run Workflow.
    /// Nothing between the left verbs and the Metadata · Sort · Filter cluster (`panes.chrome.one-filter-pattern`):
    /// Export is File › Export, Run Workflow left the bar, the filters are in the Filter field's menu.
    private var secondaryBarButtons: some View { EmptyView() }

    private var condensedBarButtons: some View { EmptyView() }

    /// The import picker, for the folder this pane shows (never the library root, #4449); `.link` keeps files in place.
    func openImportPicker() {
        fileImportMode = .link
        fileImportTargetFolderId = folderId
        showingFileImporter = true
    }

    private func handleCreateNewFolder() {
        guard libraryManager.globalLibrary != nil else { return }
        // Creation lives on the library's document store; no sidebarState here.
        Task {
            guard let library = libraryManager.getLibrary(id: windowState.libraryId)
                ?? libraryManager.globalLibrary else { return }
            do {
                // `folderId` — never the deprecated root-only `createCollection`
                // (#4449): a folder created while browsing a subfolder must land
                // IN that subfolder, not the library root.
                _ = try await library.documentStore.createFolder(name: "New Folder", parentId: folderId)
                await library.documentStore.refresh()
            } catch {
                bottomBarLogger.error("Failed to create folder from bottom bar: \(error.localizedDescription)")
            }
        }
    }

    /// The ONE import handler every `showingFileImporter` presenter in this
    /// view shares (#4449, #4452) — bottom bar, folder contextual menu, and
    /// the Data-menu Import submenu (via `libraryImportAction`) alike.
    /// Always imports into `fileImportTargetFolderId` with
    /// `fileImportMode`, both of which each presenter sets before flipping
    /// `showingFileImporter = true`; never a bare `parentId: nil` that
    /// silently lands documents at the library root.
    func handleFileImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            let targetFolderId = fileImportTargetFolderId
            let mode = fileImportMode
            Task { @MainActor in
                guard let library = libraryManager.getLibrary(id: windowState.libraryId)
                    ?? libraryManager.globalLibrary else { return }
                do {
                    let outcome = try await library.importService.importFiles(urls, mode: mode, parentId: targetFolderId)
                    await library.documentStore.refreshUnlessLiveDelivery(
                        streamConnected: library.changeStream.isConnected
                    )
                    // #3276: this returns normally when SOME files failed, so
                    // without this the shared importer handler reported a
                    // partial loss as a clean import.
                    if let message = outcome.partialFailureMessage {
                        bottomBarLogger.error("Import completed partially: \(message)")
                        importErrorMessage = message
                    }
                } catch {
                    bottomBarLogger.error("Import failed: \(error.localizedDescription)")
                    importErrorMessage = "Import failed: \(error.localizedDescription)"
                }
            }
        case .failure(let error):
            bottomBarLogger.debug("Import cancelled or failed: \(error.localizedDescription)")
        }
    }

}
