import SwiftUI

// MARK: - ContentView Preview Modes & Lifecycle

extension ContentView {

    /// Restore-time clamp for the persisted inspector width: the exact bounds
    /// the splitter enforces (`inspectorMinWidth...inspectorMaxWidth`), so a
    /// user-dragged width survives relaunch instead of being squeezed by a
    /// divergent hardcoded cap (#4287). Pure and `nonisolated` so tests pin it
    /// off-main (View statics inherit MainActor under the macOS 26 SDK).
    nonisolated static func restoredInspectorWidth(_ raw: Double) -> Double {
        min(max(raw, inspectorMinWidth), inspectorMaxWidth)
    }

    /// Extracted from the view's `.onAppear` closure to keep `ContentView.body`
    /// within the Swift type-checker's complexity budget (the inline closure
    /// pushed the whole body over the "unable to type-check in reasonable time"
    /// limit). Pure setup/state-restore work — no view building.
    func handleOnAppear() {
        // Restore all persisted state from @SceneStorage
        restorePersistedState()
        if focusedPane == nil {
            focusedPane = .content
        }
        // Clamp to a sane range. SceneStorage can hold stale/corrupted values
        // from previous sessions (e.g., values written during layout animations).
        // Clamps to the SAME bounds the splitter enforces (#4287) — a stray
        // hardcoded 400 here silently shrank a user's wider pane every launch.
        inspectorWidth = Self.restoredInspectorWidth(inspectorWidth)
        contentWidth = min(
            max(contentWidth, ContentView.contentMinWidth),
            ContentView.contentMaxWidth
        )
        // Inspector visibility is per-window (@SceneStorage) and reaches the
        // View menu via FocusedValues.showInspector — no app-wide seeding needed (#1451).
        updateColumnVisibility()
        viewDisplayMode = normalizedViewDisplayMode(viewDisplayMode)
        viewSettings.previewMode = normalizedPreviewMode(viewSettings.previewMode)
        let initialLayoutMode: LayoutMode = switch viewSettings.previewMode {
        case .none: .none
        case .standard: .standard
        case .widescreen: .widescreen
        }
        if currentLayoutMode != initialLayoutMode {
            currentLayoutMode = initialLayoutMode
        }

        // If documents were already loaded before onAppear, restore
        // the preview selection now (the onChange handler won't fire).
        if detailDocument == nil, !documentStore.currentDocuments.isEmpty {
            // Document-order primary, never Set.first (F3, 2026-08-09).
            let firstSelectedId = shellPrimarySelectionId(
                in: browserSelection, orderedBy: documentStore.currentDocuments
            )
            if let firstSelectedId {
                NavTrace.log("statePreview.restore", "\(firstSelectedId)")
                detailDocument = documentStore.currentDocuments.first(where: { $0.id == firstSelectedId })
            }
        }
        recordNavigationEntry()
    }

    /// Normalize a requested display mode against current feature gates.
    func normalizedViewDisplayMode(_ mode: ViewDisplayMode) -> ViewDisplayMode {
        let requestedMode: ViewDisplayMode = switch mode {
        case .workspace: .canvas
        default: mode
        }
        guard availableViewDisplayModes.contains(requestedMode) else {
            if availableViewDisplayModes.contains(.list) {
                return .list
            }
            return .icon
        }
        return requestedMode
    }

    /// Available preview/split modes for current sidebar context.
    /// Library/Search split layouts are gated for 0.0.1:
    /// keep only the side-by-side default (widescreen) when advanced split layouts are off.
    var availablePreviewModes: [PreviewMode] {
        switch sidebarMode {
        case .library:
            if Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
                return [.none, .standard]
            }
            if !featureManager.isLibrarySearchSplitLayoutsEnabled {
                return [.widescreen]
            }
            return [.none, .standard, .widescreen]
        case .chat:
            if Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
                return [.none, .standard]
            }
            return [.none, .standard, .widescreen]
        case .workflows, .automation, .activity, .research, .knowledgeGraph:
            return []
        }
    }

    /// Normalize preview mode against current feature gates.
    func normalizedPreviewMode(_ mode: PreviewMode) -> PreviewMode {
        guard availablePreviewModes.contains(mode) else {
            if availablePreviewModes.contains(.widescreen) {
                return .widescreen
            }
            if availablePreviewModes.contains(.standard) {
                return .standard
            }
            if availablePreviewModes.contains(.none) {
                return .none
            }
            return .none
        }
        return mode
    }

    /// Available layout modes mapped from preview modes for toolbar picker.
    var availableLayoutModes: [LayoutMode] {
        availablePreviewModes.map { preview in
            switch preview {
            case .none: .none
            case .standard: .standard
            case .widescreen: .widescreen
            }
        }
    }

    // MARK: - onChange Handlers — Mode & Display

    /// Handles `.onChange(of: documentStore.collections)`.
    /// Re-restores view mode once data loads (collections arrive after API responds).
    func handleCollectionsChange(
        old oldCollections: [Document],
        new newCollections: [Document]
    ) {
        guard oldCollections.isEmpty, !newCollections.isEmpty else { return }
        viewMode = restoreViewMode(type: storedViewModeType, itemId: storedViewModeItemId)
        let restoredId = Self.sidebarSelectionId(
            for: storedViewModeType,
            itemId: storedViewModeItemId
        )
        // sidebarSelectionId returns nil for "activity" with no run ID; use the
        // fixed tag so the Activity row stays highlighted after relaunch (#648).
        sidebarSelectionState.selectedItemId = restoredId ?? (storedViewModeType == "activity" ? "activity-browser" : nil)
    }

    /// Handles `.onChange(of: documentStore.currentDocuments)`.
    /// Populates and keeps detailDocument in sync when the document list refreshes.
    func handleCurrentDocumentsChange(_ newDocs: [Document]) {
        // Populate preview from restored selection whenever documents load
        if detailDocument == nil,
           // Document-order primary, never Set.first (F3, 2026-08-09).
           let firstSelectedId = shellPrimarySelectionId(in: browserSelection, orderedBy: newDocs),
           let doc = newDocs.first(where: { $0.id == firstSelectedId }) {
            detailDocument = doc
        }
        // Keep detailDocument in sync when currentDocuments refreshes
        // so the inspector shows updated page_content after workflows
        // complete. GUARDED with != (2026-08-09, the review's unguarded-
        // rewrite finding): an unconditional write re-fires every
        // detailDocument observer — including the canvas re-resolution — on
        // every list tick, even when the snapshot is identical. The sibling
        // handler below already guards for exactly this reason.
        let refreshedDetail = Self.refreshedFocusedDocument(detailDocument, in: newDocs)
        if refreshedDetail != detailDocument {
            detailDocument = refreshedDetail
        }
        let refreshedPageFocus = Self.refreshedFocusedDocument(pageFocusDocument, in: newDocs)
        if refreshedPageFocus != pageFocusDocument {
            pageFocusDocument = refreshedPageFocus
        }
    }

    /// Replace an actively-focused document snapshot with the freshly-loaded
    /// row from `newDocs` when available, otherwise keep the current snapshot.
    /// This keeps page-scoped inspector/reader state current after workflow
    /// writes without clearing focus when the row is temporarily absent.
    static func refreshedFocusedDocument(_ current: Document?, in newDocs: [Document]) -> Document? {
        guard let current else { return nil }
        return newDocs.first(where: { $0.id == current.id }) ?? current
    }

    /// Handles `.onChange(of: documentStore.revision)` (#4318).
    ///
    /// `handleCurrentDocumentsChange` only fires when `currentDocuments`
    /// itself changes — but a change-stream splice for a page child lands in
    /// `childrenCache` / `collections` (both `@ObservationIgnored`), so the
    /// focused snapshots (`detailDocument`, `pageFocusDocument`) kept stale
    /// page_content until reselection. Re-resolve them through the store's
    /// full-container lookup; the `!=` guard keeps identity stable when the
    /// batch didn't touch the focused rows.
    func handleDocumentRevisionChange() {
        if let current = detailDocument,
           let fresh = documentStore.liveDocument(id: current.id),
           fresh != current {
            detailDocument = fresh
        }
        if let current = pageFocusDocument,
           let fresh = documentStore.liveDocument(id: current.id),
           fresh != current {
            pageFocusDocument = fresh
        }
    }

    /// Handles `.onChange(of: viewSettings.previewMode)`.
    /// Syncs View-menu changes back to the toolbar layout picker.
    func handlePreviewModeChange(_ newPreviewMode: PreviewMode) {
        // Sync View menu changes back to toolbar layout picker
        let effectivePreviewMode = normalizedPreviewMode(newPreviewMode)
        if effectivePreviewMode != newPreviewMode {
            viewSettings.previewMode = effectivePreviewMode
        }

        let newLayoutMode = switch effectivePreviewMode {
        case .none: LayoutMode.none
        case .standard: LayoutMode.standard
        case .widescreen: LayoutMode.widescreen
        }

        if currentLayoutMode != newLayoutMode {
            withAnimation(FrameAnimation.snappy) {
                currentLayoutMode = newLayoutMode
            }
        }
    }

    /// Handles `.onChange(of: viewDisplayMode)`.
    /// Syncs toolbar picker changes to viewSettings.libraryLayout (#1215).
    func handleViewDisplayModeChange(_ newMode: ViewDisplayMode) {
        let newLayout = newMode.libraryLayout
        if viewSettings.libraryLayout != newLayout {
            viewSettings.libraryLayout = newLayout
        }
    }

    /// Handles `.onChange(of: viewSettings.libraryLayout)`.
    /// Syncs View-menu changes back to the toolbar view mode picker.
    func handleLibraryLayoutChange(_ newLibraryLayout: LibraryLayout) {
        // Sync View menu changes back to toolbar view mode picker.
        let newDisplayMode = newLibraryLayout.displayMode
        let effectiveDisplayMode = normalizedViewDisplayMode(newDisplayMode)

        if effectiveDisplayMode != newDisplayMode {
            viewSettings.libraryLayout = effectiveDisplayMode.libraryLayout
        }

        if viewDisplayMode != effectiveDisplayMode {
            viewDisplayMode = effectiveDisplayMode
        }
    }

    /// Handles `.onChange(of: viewMode)`.
    /// Auto-saves workflow on transition, persists view mode, records navigation entry.
    func handleViewModeChange(old oldMode: AppViewMode, new newMode: AppViewMode) {
        guard !isRestoringNavigationHistory else { return }
        // Auto-save only when leaving the currently edited workflow.
        // Skip workflow->same-workflow transitions (e.g., sidebar rename refresh),
        // which can otherwise overwrite a fresh rename with stale editor state.
        let shouldAutoSaveWorkflow: Bool = {
            guard case .workflow(let oldWorkflow) = oldMode, let oldWorkflow else {
                return false
            }

            switch newMode {
            case .workflow(let newWorkflow):
                guard let newWorkflow else {
                    return false
                }
                return newWorkflow.id != oldWorkflow.id
            default:
                return true
            }
        }()

        if shouldAutoSaveWorkflow, case .workflow(let oldWorkflow) = oldMode, let workflow = oldWorkflow {
            // Capture the editing workflow content before it changes
            let workflowToSave = editingWorkflow
            Task { @MainActor in
                await autoSaveWorkflow(workflowId: workflow.id, workflow: workflowToSave)
            }
        }

        // Persist view mode to @SceneStorage
        let (type, id) = Self.serializeViewMode(newMode)
        storedViewModeType = type
        storedViewModeItemId = id
        recordNavigationEntry()
    }

    /// Handles `.onChange(of: sidebarMode)`.
    /// Re-normalizes view/preview/layout modes for the new sidebar context.
    static func libraryLayout(for mode: ViewDisplayMode) -> LibraryLayout {
        switch mode {
        case .icon: return .icons
        case .list: return .list
        case .table: return .table
        case .columns: return .columns
        case .canvas, .space, .workspace: return .canvas
        }
    }

    func handleSidebarModeChange() {
        // TAKEOVER modes (workflows/automation/activity/research/KG) have no
        // preview at all — availablePreviewModes is empty and the layout
        // ignores previewMode there. Normalizing ANYWAY overwrote the STORED
        // preview setting to .none, so returning to the library kept the
        // preview hidden (Daniel, 2026-08-10: "when I am in a node editor
        // and then go back to a file, the preview is hidden — there's
        // something not remembering what's open"). A mode with nothing to
        // normalize must leave the user's layout memory alone.
        guard !availablePreviewModes.isEmpty else { return }
        viewDisplayMode = normalizedViewDisplayMode(viewDisplayMode)
        viewSettings.libraryLayout = Self.libraryLayout(for: viewDisplayMode)

        let effectivePreviewMode = normalizedPreviewMode(viewSettings.previewMode)
        if effectivePreviewMode != viewSettings.previewMode {
            viewSettings.previewMode = effectivePreviewMode
        }

        let effectiveLayoutMode: LayoutMode = switch effectivePreviewMode {
        case .none: .none
        case .standard: .standard
        case .widescreen: .widescreen
        }
        if currentLayoutMode != effectiveLayoutMode {
            currentLayoutMode = effectiveLayoutMode
        }
    }
}
