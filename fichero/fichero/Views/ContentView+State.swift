import OSLog
import SwiftUI

// MARK: - ContentView State Management Extension
// Agent: StateManagementAgent
// Responsibility: All @State, @SceneStorage, @EnvironmentObject properties and computed properties

extension ContentView {

    // MARK: - Computed Properties

    /// Toolbar/window title showing only the current view/item name
    var toolbarTitle: String {
        let viewName: String
        switch viewMode {
        case .library(let document):
            viewName = document?.name ?? "Library"
        case .search(let savedSearch):
            viewName = savedSearch?.name ?? "Search"
        case .chat(let conversation):
            viewName = conversation?.title ?? "Chat"
        case .comparison(let comparison):
            if let comp = comparison {
                let truncated = comp.prompt.count > 30 ? String(comp.prompt.prefix(30)) + "..." : comp.prompt
                viewName = truncated
            } else {
                viewName = "Comparison"
            }
        case .workflow(let workflow):
            viewName = workflow?.name ?? "Workflow"
        case .chain(let chain):
            viewName = chain?.name ?? "Chain"
        case .batches:
            viewName = "Activity"
        case .batch:
            viewName = "Activity"
        case .automation:
            viewName = "Automation"
        case .schedule(let schedule):
            viewName = schedule?.name ?? "Schedule"
        case .trigger(let trigger):
            viewName = trigger?.name ?? "Trigger"
        case .activity(let selectedRun):
            if let run = selectedRun {
                viewName = run.name
            } else {
                viewName = "Activity"
            }
        case .mindPalace:
            viewName = "Mind Palace"
        }

        return viewName
    }

    /// SF symbol name for the current view mode — shown alongside toolbarTitle in the navigation header
    var toolbarIcon: String {
        switch viewMode {
        case .library(let document):
            guard let doc = document else { return "books.vertical" }
            return doc.docType == .folder ? "folder" : "doc.text"
        case .search:
            return "magnifyingglass"
        case .chat:
            return "bubble.left.and.bubble.right"
        case .comparison:
            return "rectangle.split.2x1"
        case .workflow:
            return "bolt"
        case .chain:
            return "link"
        case .batches, .batch, .activity:
            return "clock"
        case .automation:
            return "gearshape.2"
        case .schedule:
            return "calendar"
        case .trigger:
            return "bolt.circle"
        case .mindPalace:
            return "cube.transparent"
        }
    }

    /// Documents for the browser based on current library selection
    var selectedDocuments: [Document] {
        return documentStore.currentDocuments
    }

    /// Document to show in inspector. Precedence:
    ///   1. Grid selection — the leaf the user just clicked in the grid.
    ///   2. The viewMode's associated doc — the folder the user has open
    ///      in the sidebar (set by handleSelection on sidebar click).
    ///   3. detailDocument — legacy fallback for navigated-into doc state
    ///      that may not be cleared on every sidebar transition.
    /// (#712)
    var inspectorDocument: Document? {
        // What folder, if any, is the sidebar pointing at right now?
        let currentSidebarFolder: Document? = {
            if case .library(let doc) = viewMode { return doc }
            return nil
        }()

        // 1. Grid selection — but ONLY if the selected doc actually
        //    belongs to the current sidebar folder. A stale or cross-
        //    folder browserSelection (e.g. left over from a previous
        //    folder, or auto-set when the grid first loaded) must NOT
        //    shadow the sidebar-selected folder. (#712)
        if let firstId = browserSelection.first,
           let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }),
           doc.parentId == currentSidebarFolder?.id {
            return doc
        }
        // 2. Page document — PDF reading context (#1366). When the user
        //    has scrolled to a specific page (syncGridSelectionToPDFPage),
        //    detailDocument is that page. The sidebar folder must not shadow
        //    it: the inspector needs the page doc so its KG tab shows the
        //    per-page entities the backend now writes per page doc_id.
        if let pageDoc = detailDocument, pageDoc.docType == .page {
            return pageDoc
        }
        // 3. Sidebar viewMode's folder doc.
        if let folder = currentSidebarFolder {
            return folder
        }
        // 4. Legacy fallback.
        return detailDocument
    }

    /// Whether we're in workflow mode
    var isWorkflowMode: Bool {
        if case .workflow = viewMode { return true }
        return false
    }

    /// Whether to show the navigation toolbar (layout/view pickers, add button)
    /// Only show for content modes (library, search, chat, workflows)
    var showNavigationToolbar: Bool {
        switch viewMode {
        case .library, .search, .chat, .comparison, .workflow, .chain:
            return true
        case .batches, .batch, .automation, .schedule, .trigger, .activity, .mindPalace:
            return false
        }
    }

    /// Whether to show the inspector toggle button.
    /// Keep this available across modes so inspector visibility is
    /// controlled by persistent window state, not current selection/view.
    var showInspectorToggle: Bool {
        true
    }

    /// Whether to show the view mode picker (icon/list/table/map)
    /// Shown for modes that support multiple content presentations.
    var showViewModePicker: Bool {
        switch sidebarMode {
        case .library, .search, .workflows:
            return true
        case .chat, .automation, .activity, .mindPalace, .research, .knowledgeGraph:
            return false
        }
    }

    /// Whether to show the layout mode picker (none/standard/widescreen)
    /// Only show for modes that have preview panes
    var showLayoutPicker: Bool {
        availablePreviewModes.count > 1
    }

    /// Available display modes for the current sidebar mode.
    /// Library is icon-only in 0.0.1 unless advanced views are explicitly enabled.
    var availableViewDisplayModes: [ViewDisplayMode] {
        switch sidebarMode {
        case .library:
            if let doc = libraryViewDocument, doc.docType == .folder || doc.isWorkspace {
                return [.icon, .list, .map, .realitykit]
            }
            if !featureManager.isLibraryAdvancedViewsEnabled {
                return [.icon]
            }
            return [.icon, .list, .table, .map]
        case .search:
            if !featureManager.isSearchAdvancedViewsEnabled {
                return [.list]
            }
            return [.icon, .list, .table, .map]
        case .workflows:
            // Keep workflow editor simple by default; only expose table mode
            // when advanced views are explicitly enabled.
            if !featureManager.isWorkflowEditorAdvancedViewsEnabled {
                return [.icon, .list]
            }
            return [.icon, .list, .table]
        case .chat, .automation, .activity, .mindPalace, .research, .knowledgeGraph:
            return [.icon]
        }
    }

    var libraryViewDocument: Document? {
        if case .library(let doc) = viewMode { return doc }
        return nil
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
        // 400 is a generous practical maximum for an inspector panel.
        inspectorWidth = min(max(inspectorWidth, ContentView.inspectorMinWidth), 400)
        contentWidth = min(
            max(contentWidth, ContentView.contentMinWidth),
            ContentView.contentMaxWidth
        )
        if !featureManager.isSearchEnabled && sidebarMode == .search {
            sidebarMode = .library
            viewMode = .library(nil)
        }
        // Sync View menu inspector command to per-window inspector state.
        if viewSettings.showInspector != showInspectorSidebar {
            viewSettings.showInspector = showInspectorSidebar
        }
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
            let firstSelectedId = browserSelection.first
            if let firstSelectedId {
                detailDocument = documentStore.currentDocuments.first(where: { $0.id == firstSelectedId })
            }
        }
        recordNavigationEntry()
    }

    /// Normalize a requested display mode against current feature gates.
    func normalizedViewDisplayMode(_ mode: ViewDisplayMode) -> ViewDisplayMode {
        guard availableViewDisplayModes.contains(mode) else {
            if availableViewDisplayModes.contains(.list) {
                return .list
            }
            return .icon
        }
        return mode
    }

    /// Available preview/split modes for current sidebar context.
    /// Library/Search split layouts are gated for 0.0.1:
    /// keep only the side-by-side default (widescreen) when advanced split layouts are off.
    var availablePreviewModes: [PreviewMode] {
        switch sidebarMode {
        case .library, .search:
            if !featureManager.isLibrarySearchSplitLayoutsEnabled {
                return [.widescreen]
            }
            return [.none, .standard, .widescreen]
        case .chat:
            return [.none, .standard, .widescreen]
        case .workflows, .automation, .activity, .mindPalace, .research, .knowledgeGraph:
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

    // MARK: - onChange Handlers
    // Extracted from mainContentView body to reduce type-checker complexity.

    /// Handles `.onChange(of: documentStore.collections)`.
    /// Re-restores view mode once data loads (collections arrive after API responds).
    func handleCollectionsChange(
        old oldCollections: [Document],
        new newCollections: [Document]
    ) {
        guard oldCollections.isEmpty, !newCollections.isEmpty else { return }
        viewMode = restoreViewMode(type: storedViewModeType, itemId: storedViewModeItemId)
        let restoredId = sidebarSelectionId(
            for: storedViewModeType,
            itemId: storedViewModeItemId
        )
        // sidebarSelectionId returns nil for "activity" with no run ID; use the
        // fixed tag so the Activity row stays highlighted after relaunch (#648).
        selectedSidebarItemId = restoredId ?? (storedViewModeType == "activity" ? "activity-browser" : nil)
    }

    /// Handles `.onChange(of: documentStore.currentDocuments)`.
    /// Populates and keeps detailDocument in sync when the document list refreshes.
    func handleCurrentDocumentsChange(_ newDocs: [Document]) {
        // Populate preview from restored selection whenever documents load
        if detailDocument == nil,
           let firstSelectedId = browserSelection.first,
           let doc = newDocs.first(where: { $0.id == firstSelectedId }) {
            detailDocument = doc
        }
        // Keep detailDocument in sync when currentDocuments refreshes
        // so the inspector shows updated page_content after workflows complete.
        if let currentDetail = detailDocument,
           let updatedDoc = newDocs.first(where: { $0.id == currentDetail.id }) {
            detailDocument = updatedDoc
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
            withAnimation {
                currentLayoutMode = newLayoutMode
            }
        }
    }

    /// Handles `.onChange(of: viewSettings.libraryLayout)`.
    /// Syncs View-menu changes back to the toolbar view mode picker.
    func handleLibraryLayoutChange(_ newLibraryLayout: LibraryLayout) {
        // Sync View menu changes back to toolbar view mode picker
        let newDisplayMode = switch newLibraryLayout {
        case .icons: ViewDisplayMode.icon
        case .list: ViewDisplayMode.list
        case .table: ViewDisplayMode.table
        case .map: ViewDisplayMode.map
        }
        let effectiveDisplayMode = normalizedViewDisplayMode(newDisplayMode)

        if effectiveDisplayMode != newDisplayMode {
            viewSettings.libraryLayout = switch effectiveDisplayMode {
            case .icon: .icons
            case .list: .list
            case .table: .table
            case .map, .realitykit: .map
            }
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
        let (type, id) = serializeViewMode(newMode)
        storedViewModeType = type
        storedViewModeItemId = id
        recordNavigationEntry()
    }

    /// Handles `.onChange(of: selectedSidebarItemId)`.
    /// Restores per-folder view mode and drives the inspector from sidebar selection.
    func handleSidebarSelectionChange(_ newFolderId: String?) {
        if isRestoringNavigationHistory { return }
        // Restore per-folder view mode when switching folders.
        // Priority: per-folder save > global default > current
        // SceneStorage value. The global default protects against
        // the "revert to Icon when no per-folder save exists"
        // complaint in #943.
        if let saved = displayMode(for: newFolderId) {
            viewDisplayMode = normalizedViewDisplayMode(saved)
        } else {
            let normalizedDefault = normalizedViewDisplayMode(defaultLibraryViewDisplayMode)
            if viewDisplayMode != normalizedDefault {
                viewDisplayMode = normalizedDefault
            }
        }

        // Clear grid selection on sidebar folder change so the folder
        // inspector shows by default. Without this, a stale browserSelection
        // from a previous folder can resolve to a child of the new folder
        // (when ids happen to be present in the new folder's children),
        // suppressing the folder inspector. (#712)
        browserSelection.removeAll()

        // Drive the inspector from sidebar selection so clicking a folder
        // (or any document row) in the sidebar populates the inspector.
        // Sidebar IDs are prefixed "doc:UUID" — extract the bare doc ID
        // before looking up. (#696 — folder inspector blank after sidebar
        // click. MEMORY: SidebarItem.id is 'doc:UUID', strip prefix.)
        guard let prefixedId = newFolderId,
              prefixedId.hasPrefix("doc:") else { return }
        let docId = String(prefixedId.dropFirst("doc:".count))
        // Force-clear any previewed document immediately so the inspector
        // reflects the newly-selected folder before the async applyDoc
        // resolution completes. Without this, detailDocument stays set to
        // the previously-previewed file and inspectorDocument step 1 can
        // match it against the stale browserSelection. (#795)
        detailDocument = nil
        // Closure to apply a resolved Document — sets detailDocument (#961).
        // Folders now keep the current layout so the WebKit/reading pane
        // stays visible for folder-level aggregate content (#1405).
        let applyDoc: (Document) -> Void = { doc in
            // Defer mutations to next run loop turn to avoid triggering
            // multiple FocusedValue updates in the same render cycle (#961).
            DispatchQueue.main.async {
                detailDocument = doc
            }
        }
        if detailDocument?.id != docId {
            if let doc = documentStore.currentDocuments.first(where: { $0.id == docId }) {
                applyDoc(doc)
            } else {
                Task { @MainActor in
                    let fetched: Document? = try? await documentStore.api.get(
                        "/documents/\(docId)"
                    )
                    if let fetched, selectedSidebarItemId == prefixedId {
                        applyDoc(fetched)
                    }
                }
            }
        }
    }

    /// Handles `.onChange(of: sidebarMode)`.
    /// Re-normalizes view/preview/layout modes for the new sidebar context.
    func handleSidebarModeChange() {
        viewDisplayMode = normalizedViewDisplayMode(viewDisplayMode)
        viewSettings.libraryLayout = switch viewDisplayMode {
        case .icon: .icons
        case .list: .list
        case .table: .table
        case .map, .realitykit: .map
        }

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

    /// Handles `.onChange(of: columnVisibility)`.
    /// Persists column visibility and keeps explicit sidebar state in sync.
    func handleColumnVisibilityChange(_ newVisibility: NavigationSplitViewVisibility) {
        // Persist column visibility to @SceneStorage
        // Map NavigationSplitViewVisibility to raw int for @SceneStorage
        if newVisibility == .automatic {
            columnVisibilityRaw = 0
        } else if newVisibility == .detailOnly {
            columnVisibilityRaw = 1
        } else if newVisibility == .all {
            columnVisibilityRaw = 2
        } else if newVisibility == .doubleColumn {
            columnVisibilityRaw = 3
        } else {
            columnVisibilityRaw = 0
        }

        // Keep explicit left-sidebar state in sync with split-view visibility.
        // In this app's layout, `.doubleColumn` is sidebar + content.
        if newVisibility == .detailOnly {
            showSidebar = false
        } else if newVisibility == .all || newVisibility == .doubleColumn || newVisibility == .automatic {
            showSidebar = true
        }
    }

    /// Handles `.onChange(of: browserSelection)`.
    /// Persists browser selection to @SceneStorage.
    func handleBrowserSelectionChange(_ newSelection: Set<String>) {
        // Persist browser selection to @SceneStorage
        if let encoded = try? JSONEncoder().encode(newSelection) {
            browserSelectionData = encoded
        }
        // Note: previously this auto-synced detailDocument from selection
        // so single-clicks in the grid would swap the preview pane. Per
        // Daniel's intended click model (#772): single-click should only
        // update the right inspector (via inspectorDocument's
        // browserSelection priority), NOT the preview pane. detailDocument
        // is now only mutated by handleDoubleClick (and explicit
        // openSelectedDocument keyboard shortcut + sidebar selection).
    }

    /// Handles `.onChange(of: detailDocument)`.
    /// Keeps documentStore.selectedDocument in sync and records navigation.
    func handleDetailDocumentChange(_ newDoc: Document?) {
        // Keep documentStore.selectedDocument in sync so WorkflowEditor
        // toolbar button sees the current document at run time.
        documentStore.selectedDocument = newDoc
        guard !isRestoringNavigationHistory else { return }
        recordNavigationEntry()
    }

    /// Handles `.onReceive` of `NSApplication.willTerminateNotification`.
    /// Auto-saves the editing workflow when the app quits.
    func handleWillTerminate() {
        // Auto-save workflow when app quits
        if case .workflow(let workflow) = viewMode, let workflowItem = workflow {
            let workflowToSave = editingWorkflow
            Task { @MainActor in
                await autoSaveWorkflow(workflowId: workflowItem.id, workflow: workflowToSave)
            }
        }
    }

    /// Handles `.onReceive` of `.ficheroEntitySearchRequested`.
    /// Fires the toolbar search for an entity-lozenge click.
    func handleEntitySearchRequested(_ note: Notification) {
        // Click on a blue entity lozenge anywhere in the UI fires the
        // toolbar search for that name. Same code path as typing in
        // the toolbar — creates a saved search, switches to search
        // mode, runs the query.
        //
        // When the lozenge knows its entity_type (people / places /
        // keywords / etc.), we construct a SCOPED query like
        // `keywords:"social license"` so the search hits only that
        // artifact type — exactly the docs the user is asking about.
        // Free-text fallback when the type isn't tagged so older
        // call sites still work.
        guard let name = note.userInfo?["name"] as? String,
              !name.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        let entityType = note.userInfo?["entityType"] as? String
        let query: String
        if let entityType, !entityType.isEmpty {
            let needsQuoting = name.contains(" ")
            query = needsQuoting
                ? "\(entityType):\"\(name)\""
                : "\(entityType):\(name)"
        } else {
            query = name
        }
        toolbarSearchText = query
        runToolbarSearch(query)
    }

    /// Handles `.onReceive` of `.ficheroOpenClaimSource`.
    /// Navigates to a claim's source document with the page scrolled into view.
    func handleOpenClaimSource(_ note: Notification) {
        // Claim card source-doc link → navigate to the document
        // with the page scrolled into view. userInfo carries
        // documentId (required) + pageLabel / charStart / charEnd /
        // claimId (all optional). For now this lights up doc
        // selection + posts an internal navigation event the
        // PDF preview will consume to scroll to pageLabel. The
        // highlight-span overlay lands in a later phase (#995). (#978/#979/#982)
        guard let info = note.userInfo,
              let docId = info["documentId"] as? String else { return }
        // Switch to library view if we're in another mode (KG /
        // Activity / Workflow) — the source preview lives there.
        if sidebarMode != .library {
            sidebarMode = .library
        }
        showInspectorSidebar = true
        focusedPane = .inspector
        if let claimId = info["claimId"] as? String {
            claimFocusState.selectClaim(
                claimId: claimId,
                claimText: (info["claimText"] as? String) ?? (info["excerpt"] as? String),
                sourceDocumentId: docId,
                pageLabel: info["pageLabel"] as? String,
                charStart: info["charStart"] as? Int,
                charEnd: info["charEnd"] as? Int
            )
        }
        // Resolve page-child source documents to their parent file and
        // select it. Then forward the page-navigation request that
        // PDFPageView consumes for scrolling/highlighting.
        Task { @MainActor in
            await navigateToSourcePage(docId)
            NotificationCenter.default.post(
                name: .ficheroNavigateToPage,
                object: nil,
                userInfo: info
            )
        }
    }
}
