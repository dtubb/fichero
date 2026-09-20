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

            // Translucent Liquid Glass background, matching the sidebar mini-toolbars
            // (SidebarModeBar / SidebarBottomToolbar / PaneFilterBar) for a consistent
            // glass look across the window chrome (#2550).
            GlassEffectContainer {
                AdaptiveMiniToolbarRow {
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
                    bottomBarOverflowMenu
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
                    librarySortMenu(iconOnly: false)
                    libraryShowMenu(iconOnly: false)
                    libraryFilterToggleButton(iconOnly: false)
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
                }
                .padding(.horizontal, 10)
                .frame(height: bottomBarHeight)
                // ONE control size for the whole bar (Daniel, 2026-08-24:
                // the +/− size is the right one; the sort/metadata cluster
                // rendered .regular). Environment value — every child
                // inherits; the per-button repeats are deleted.
                .controlSize(.small)
                        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
            }
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
        // #4966: ONE popover presenter for the KG filter, attached to the
        // bar's own outer container so it survives whichever `ViewThatFits`
        // rung (condensed button or overflow-menu row) actually triggered
        // it — attaching it to either trigger individually would vanish
        // along with that trigger the moment the OTHER rung renders instead.
        .popover(isPresented: $showingKgFilterPopover) {
            HStack(spacing: 6) { kgContentFilterControls }
                .padding(10)
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

    /// #4856: the filter slot — the SAME text field + type menu
    /// `EntitiesLibraryContent`/`ClaimsLibraryContent` used to draw in their
    /// own second bar, now filled into this ONE bar instead. The content
    /// view still owns the filter's MEANING (it reports `onAvailableTypesChanged`
    /// and reads `filterText`/`filterType` back) — only where the controls
    /// DRAW has moved.
    ///
    /// #4966: moved OUT of the always-inline essential tier — a 220pt
    /// `TextField` cannot shrink, so leaving it essential would make it the
    /// one thing in this bar that still overflows a narrow pane. It now
    /// lives in the secondary/condensed/overflow rungs below, the same
    /// ladder `entityFilterMenu` already rode for list mode.
    @ViewBuilder
    private var kgContentFilterControls: some View {
        Image(systemName: "line.3.horizontal.decrease.circle")
            .foregroundStyle(.secondary)
        TextField(
            effectiveContentKind == .claims ? "Filter claims" : "Filter entities",
            text: $kgContentFilterText
        )
        .textFieldStyle(.roundedBorder)
        .frame(maxWidth: 220)
        Menu {
            Button("All types") { kgContentFilterType = nil }
            Divider()
            ForEach(kgContentAvailableTypes, id: \.self) { type in
                Button(type.capitalized) { kgContentFilterType = type }
            }
        } label: {
            Label(kgContentFilterType?.capitalized ?? "All types", systemImage: "tag")
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    /// #4966: the filter's CONDENSED coat — a live `TextField` cannot fold
    /// into an icon (nothing to show) or a menu row (AppKit doesn't host an
    /// editable field inside a `Menu`'s content the way it hosts a `Menu`
    /// inside one), so this rung and the overflow rung both collapse to ONE
    /// button that opens the exact same `kgContentFilterControls` in a
    /// popover — the "a filter button that opens a popover" shape, reusing
    /// the ladder's existing `condensed`/`overflowMenu` slots rather than a
    /// second collapse mechanism.
    private var kgContentFilterPopoverButton: some View {
        Button {
            showingKgFilterPopover = true
        } label: {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .accessibilityLabel(effectiveContentKind == .claims ? "Filter claims" : "Filter entities")
        }
        .buttonStyle(.borderless)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help(effectiveContentKind == .claims ? "Filter claims" : "Filter entities")
        // The popover itself is NOT attached here (#4966): `ViewThatFits`
        // mounts only ONE ladder rung at a time, so a `.popover` on a
        // condensed-only button would vanish from the tree — and with it,
        // its anchor — the moment the overflow rung renders instead. It is
        // attached once, on the bar's own outer container in
        // `libraryBottomActionBar`, which is mounted regardless of which
        // rung is showing.
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
        Button {
            performAdd()
        } label: {
            Image(systemName: "plus")
                .accessibilityLabel(addButtonLabel)
        }
        .buttonStyle(.borderless)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help(addButtonHelp)
        .accessibilityIdentifier(addButtonAccessibilityIdentifier)

        Button {
            promptDeleteSelected()
        } label: {
            Image(systemName: "minus")
                .accessibilityLabel("Delete")
        }
        .buttonStyle(.borderless)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Delete selection")
        .disabled(isShowingEntitiesCollection || selection.isEmpty)

        Button {
            // Targets the folder this pane is currently showing, never the
            // library root (#4449) — `folderId` is nil only when browsing
            // the library's own top level, which IS the root. Explicit
            // `.link` (#4452 added Copy/Move via the Data menu) — this
            // button has always meant "link in place".
            fileImportMode = .link
            fileImportTargetFolderId = folderId
            showingFileImporter = true
        } label: {
            Image(systemName: "square.and.arrow.down")
                .accessibilityLabel("Import")
        }
        .buttonStyle(.borderless)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Import files")

        Spacer()
    }

    /// Secondary verbs — inline on Mac when they fit, else the `…` menu; menu-only
    /// on compact (#3057): the KG content filter (Entities/Claims), the
    /// entity filter (list mode), Export BibTeX, Run Workflow.
    @ViewBuilder
    private var secondaryBarButtons: some View {
        if effectiveContentKind != .documents {
            kgContentFilterControls
        }

        if displayMode == .list {
            entityFilterMenu
        }

        exportBibtexBarButton

        runWorkflowBarButton
    }

    /// The condensed mirror of the secondary tier — the SAME buttons, with the
    /// entity filter's words dropped and the KG filter folded to its popover
    /// button (#4966: a `TextField` has no icon-only coat to drop into). The
    /// export/workflow verbs are already icon-only, so they are shared
    /// outright rather than copied: one action, one definition (#3057's rule,
    /// kept).
    @ViewBuilder
    private var condensedBarButtons: some View {
        if effectiveContentKind != .documents {
            kgContentFilterPopoverButton
        }

        if displayMode == .list {
            entityFilterMenu
                .labelStyle(.iconOnly)
                .accessibilityLabel("Filter by Entity")
        }

        exportBibtexBarButton

        runWorkflowBarButton
    }

    private var exportBibtexBarButton: some View {
        Button {
            Task { await exportSelectedBibtex() }
        } label: {
            Image(systemName: "square.and.arrow.up")
        }
        .accessibilityLabel("Export BibTeX")
        .buttonStyle(.borderless)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Export selection as BibTeX")
        .disabled(isShowingEntitiesCollection || selection.isEmpty)
    }

    private var runWorkflowBarButton: some View {
        Button {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        } label: {
            Image(systemName: "bolt")
                .accessibilityLabel("Run Workflow")
        }
        .buttonStyle(.borderless)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Run workflow on selection")
        .disabled(isShowingEntitiesCollection || selection.isEmpty || !featureManager.isWorkflowRunOnSelectionEnabled)
    }

    /// `Label`-based mirror of the secondary verbs for the overflow `…` menu
    /// (#3057) — same actions + disabled logic, menu-item presentation. The
    /// KG filter survives here too (#4856's "we want them there" for the
    /// sort/filter cluster, and #4966's own note that a live `TextField`
    /// cannot live inside a `Menu`'s content the way `entityFilterMenu`,
    /// itself a `Menu`, can) — as the same popover-opening button the
    /// condensed rung uses, not a menu row.
    @ViewBuilder
    private var bottomBarOverflowMenu: some View {
        if effectiveContentKind != .documents {
            Button {
                showingKgFilterPopover = true
            } label: {
                Label(
                    effectiveContentKind == .claims ? "Filter Claims" : "Filter Entities",
                    systemImage: "line.3.horizontal.decrease.circle"
                )
            }
        }

        if displayMode == .list {
            entityFilterMenu
        }

        Button {
            Task { await exportSelectedBibtex() }
        } label: {
            Label("Export BibTeX", systemImage: "square.and.arrow.up")
        }
        .disabled(isShowingEntitiesCollection || selection.isEmpty)

        Button {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        } label: {
            Label("Run Workflow", systemImage: "bolt")
        }
        .disabled(isShowingEntitiesCollection || selection.isEmpty || !featureManager.isWorkflowRunOnSelectionEnabled)
    }

    private func exportSelectedBibtex() async {
        guard !selection.isEmpty else { return }
        let documentIds = Array(selection)
        guard let library = libraryManager.getLibrary(id: windowState.libraryId) else { return }

        do {
            // Route through the service wrapper instead of raw ficheroClient.api
            // (observable-data-layer, #3258); it owns the response handling.
            let bib = try await library.entityService.exportBibliographyBib(documentIds: documentIds)
            guard let saveURL = await presentBibtexSavePanel() else { return }
            try Data(bib.utf8).write(to: saveURL, options: .atomic)
        } catch {
            bottomBarLogger.error("Failed to export selected BibTeX: \(error.localizedDescription)")
        }
    }

    private func presentBibtexSavePanel() async -> URL? {
        #if canImport(AppKit)
        await withCheckedContinuation { continuation in
            let savePanel = NSSavePanel()
            savePanel.nameFieldStringValue = "selection.bib"
            if let bibType = UTType(filenameExtension: "bib") {
                savePanel.allowedContentTypes = [bibType]
            }
            savePanel.allowsOtherFileTypes = false
            savePanel.canCreateDirectories = true
            savePanel.begin { result in
                continuation.resume(returning: result == .OK ? savePanel.url : nil)
            }
        }
        #else
        return nil
        #endif
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
