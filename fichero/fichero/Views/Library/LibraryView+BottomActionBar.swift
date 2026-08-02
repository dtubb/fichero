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
                } overflowMenu: {
                    bottomBarOverflowMenu
                }
                .padding(.horizontal, 10)
                .frame(height: bottomBarHeight)
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
    }

    /// Essential verbs — always inline (#3057): New Folder, Delete, Import. The
    /// trailing Spacer keeps them left-aligned with the secondary/overflow on the
    /// right, preserving the bar's existing Finder-style layout.
    @ViewBuilder
    private var essentialBarButtons: some View {
        Button {
            handleCreateNewFolder()
        } label: {
            Image(systemName: "plus")
                .accessibilityLabel("New Folder")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Create a new folder")

        Button {
            promptDeleteSelected()
        } label: {
            Image(systemName: "minus")
                .accessibilityLabel("Delete")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
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
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Import files")

        Spacer()
    }

    /// Secondary verbs — inline on Mac when they fit, else the `…` menu; menu-only
    /// on compact (#3057): entity filter (list mode), Export BibTeX, Run Workflow.
    @ViewBuilder
    private var secondaryBarButtons: some View {
        if displayMode == .list {
            entityFilterMenu
        }

        Button {
            Task { await exportSelectedBibtex() }
        } label: {
            Image(systemName: "square.and.arrow.up")
                .accessibilityLabel("Export BibTeX")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Export selection as BibTeX")
        .disabled(isShowingEntitiesCollection || selection.isEmpty)

        Button {
            selectedDocumentIdsForBatch = Array(selection)
            showWorkflowPicker = true
        } label: {
            Image(systemName: "bolt")
                .accessibilityLabel("Run Workflow")
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .frame(minWidth: bottomBarTouchTarget, minHeight: bottomBarTouchTarget)
        .contentShape(Rectangle())
        .help("Run workflow on selection")
        .disabled(isShowingEntitiesCollection || selection.isEmpty || !featureManager.isWorkflowRunOnSelectionEnabled)
    }

    /// `Label`-based mirror of the secondary verbs for the overflow `…` menu
    /// (#3057) — same actions + disabled logic, menu-item presentation.
    @ViewBuilder
    private var bottomBarOverflowMenu: some View {
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
                    await library.documentStore.refresh()
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
