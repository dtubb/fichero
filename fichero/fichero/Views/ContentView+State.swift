// swiftlint:disable file_length
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
            // When a PDF page (or multiple pages) is selected in the grid,
            // reflect that in the window title so the user knows exactly what
            // is in context. The parent PDF comes from `document` (the sidebar-
            // selected item). Page count shows when the browser selection has
            // more than one page document.
            if let page = inspectorDocument, page.docType == .page {
                let selectedPageCount = browserSelection.filter { id in
                    documentStore.currentDocuments.first(where: { $0.id == id })?.docType == .page
                }.count
                if selectedPageCount > 1 {
                    let parentName = document?.name
                    viewName = parentName.map { "\(selectedPageCount) pages — \($0)" }
                        ?? "\(selectedPageCount) pages"
                } else {
                    let pageLabel = page.sequence.map { "Page \($0)" } ?? page.name
                    viewName = document.map { "\(pageLabel) — \($0.name)" } ?? pageLabel
                }
            } else {
                viewName = document?.name ?? "Library"
            }
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
        }

        return viewName
    }

    /// Breadcrumb trail showing full navigation path from library root to current selection.
    /// Returns "Library › Folder › Subfolder › File" or empty string if not applicable.
    /// Only for library mode; returns empty string for other modes.
    var breadcrumbSubtitle: String {
        guard case .library(let document) = viewMode, let doc = document else {
            return ""
        }

        // Build a lookup function for parent documents from currentDocuments + cache
        // ContentView is a struct (value type) — capture by value, no weak/retain-cycle concern.
        let parentLookup: BreadcrumbBuilder.DocumentLookup = { parentId in
            // Check currentDocuments first (most likely case)
            if let found = documentStore.currentDocuments.first(where: { $0.id == parentId }) {
                return found
            }
            // Fallback to collections if not found in current docs
            if let found = documentStore.collections.first(where: { $0.id == parentId }) {
                return found
            }
            return nil
        }

        let pageLabel: String? = if let page = inspectorDocument, page.docType == .page {
            page.pageThumbnailLabel
        } else {
            nil
        }

        let breadcrumb = BreadcrumbBuilder.buildBreadcrumbForLibraryMode(
            document: doc,
            pageLabel: pageLabel,
            parentLookup: parentLookup
        )

        // Return the breadcrumb minus the leaf name (which is already in navigationTitle)
        // Split on " › " and drop the last component
        let components = breadcrumb.split(separator: " › ")
        if components.count > 1 {
            return components.dropLast().joined(separator: " › ")
        }
        return ""
    }

    /// SF symbol name for the current view mode — shown alongside toolbarTitle in the navigation header
    var toolbarIcon: String {
        switch viewMode {
        case .library(let document):
            guard let doc = document else { return "books.vertical" }
            if let inspector = inspectorDocument, inspector.docType == .page {
                return "doc.richtext"
            }
            return doc.docType == .folder ? "folder" : (doc.fileType == .pdf ? "doc.richtext" : "doc.text")
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
        }
    }

    var selectionStatusText: String {
        if browserSelection.count > 1 {
            return "\(browserSelection.count) items selected"
        }
        return inspectorDocument?.name ?? toolbarTitle
    }

    var selectionPathText: String {
        let leaf = inspectorDocument?.name ?? toolbarTitle
        guard !breadcrumbSubtitle.isEmpty else { return leaf }
        return "\(breadcrumbSubtitle) › \(leaf)"
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
        // 2. Page focus — updated by scroll/page-flip via syncGridSelectionToPDFPage
        //    without touching detailDocument (#1463). Shows per-page KG/content
        //    while the WebKit pane stays pinned to the parent container.
        if let pageFocusDoc = pageFocusDocument {
            return pageFocusDoc
        }
        // 2b. Legacy: detailDocument may still be a page doc if set by direct
        //    navigation (double-click a page child) rather than scroll sync.
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
        case .batches, .batch, .automation, .schedule, .trigger, .activity:
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
        case .chat, .automation, .activity, .research, .knowledgeGraph:
            return false
        }
    }

    /// Whether to show the layout mode picker (none/standard/widescreen)
    /// Only show for modes that have preview panes
    var showLayoutPicker: Bool {
        availablePreviewModes.count > 1
    }

    /// Library/Search own the stable reading workspace: Library/List,
    /// Document Canvas, Reading/WebKit, plus the window-level inspector.
    /// This is independent of the current layout so toolbar pane buttons
    /// don't disappear when previews are temporarily hidden.
    var supportsReadingWorkspace: Bool {
        (sidebarMode == .library && !isEntityLibrarySelection) || sidebarMode == .search
    }

    /// Available display modes for the current sidebar mode.
    /// Library is icon-only in 0.0.1 unless advanced views are explicitly enabled.
    var availableViewDisplayModes: [ViewDisplayMode] {
        switch sidebarMode {
        case .library:
            if isEntityLibrarySelection {
                return [.list]
            }
            if let doc = libraryViewDocument,
               doc.docType == .folder || doc.isWorkspace ||
               (doc.docType == .file && doc.fileType.map { [.pdf, .word, .epub, .presentation].contains($0) } ?? false) {
                // Canvas (.canvas → Spatial2DCanvas) is the live 2D positioned-node
                // library view; Space (.space → SpaceSceneView) is the RealityKit
                // 3D renderer on the SAME shared stores (#3088). Both offered for
                // every folder/pdf/node (#2667/#3081/#3088).
                var modes: [ViewDisplayMode] = [.icon, .list, .table, .canvas, .space]
                if featureManager.isWorkspaceModeEnabled {
                    modes.append(.workspace)
                }
                return modes
            }
            if !featureManager.isLibraryAdvancedViewsEnabled {
                return [.icon]
            }
            return [.icon, .list, .table, .canvas, .space]
        case .search:
            if !featureManager.isSearchAdvancedViewsEnabled {
                return [.list]
            }
            return [.icon, .list, .table, .canvas]
        case .workflows:
            // Keep workflow editor simple by default; only expose table mode
            // when advanced views are explicitly enabled.
            if !featureManager.isWorkflowEditorAdvancedViewsEnabled {
                return [.icon, .list]
            }
            return [.icon, .list, .table]
        case .chat, .automation, .activity, .research, .knowledgeGraph:
            return [.icon]
        }
    }

    var libraryViewDocument: Document? {
        if case .library(let doc) = viewMode { return doc }
        return nil
    }

    var isEntityLibrarySelection: Bool {
        sidebarSelectionState.selectedItemId == "entities-browser"
    }

    var shellCollapsePolicy: ShellCollapsePolicy {
        Self.shellCollapsePolicy(
            windowWidth: measuredWindowWidth,
            horizontalSizeClass: horizontalSizeClass,
            sidebarVisible: showSidebar,
            inspectorVisible: showInspectorSidebar,
            detailMinWidth: paneAwareDetailMinWidth
        )
    }

    var shouldUseRuntimeSidebarCollapse: Bool {
        shellCollapsePolicy.collapseSidebar
    }

    var effectiveShowInspectorSidebar: Bool {
        showInspectorSidebar && !shellCollapsePolicy.collapseInspector
    }

    var shouldUseSplittablePane: Bool {
        Self.shouldUseSplittablePane(
            horizontalSizeClass: horizontalSizeClass,
            windowWidth: measuredWindowWidth,
            minimumWidth: paneAwareWindowMinWidth
        )
    }

    var inspectorPlacement: InspectorPlacement {
        InspectorPlacement.adaptiveDefault(horizontalSizeClass: horizontalSizeClass)
    }

    var usesDockedInspector: Bool {
        inspectorPlacement != .sheet
    }

    var paneAwareDetailMinWidth: Double {
        guard supportsReadingWorkspace else {
            return ContentView.contentMinWidth
        }

        switch currentLayoutMode {
        case .none:
            return showDocumentGrid ? ContentView.contentListMinWidth : max(ContentView.pdfCanvasMinWidth, 300)
        case .standard:
            return showDocumentGrid
                ? max(ContentView.contentListMinWidth, max(ContentView.pdfCanvasMinWidth, 300))
                : max(ContentView.pdfCanvasMinWidth, 300)
        case .widescreen:
            return adaptiveWidescreenPanePlan.minimumWidth
        }
    }

    static func adaptiveWidescreenAvailableWidth(
        windowWidth: Double?,
        inspectorVisible: Bool
    ) -> Double? {
        guard let windowWidth, windowWidth > 0 else { return nil }
        return max(0, windowWidth - (inspectorVisible ? ContentView.inspectorMinWidth : 0))
    }

    var adaptiveWidescreenPanePlan: WidescreenPanePlan {
        // Keep the reading workspace legible by dropping secondary panes as
        // the shell narrows, before SwiftUI has to overlap columns.
        let availableDetailWidth = Self.adaptiveWidescreenAvailableWidth(
            windowWidth: measuredWindowWidth,
            inspectorVisible: showInspectorSidebar
        )

        return WidescreenPanePlan.make(
            showDocumentGrid: showDocumentGrid,
            showDocumentCanvas: showDocumentCanvas,
            showReadingPane: showReadingPane,
            availableWidth: availableDetailWidth
        )
    }

    var paneAwareWindowMinWidth: Double {
        Self.windowMinWidth(
            sidebarVisible: showSidebar,
            inspectorVisible: showInspectorSidebar,
            detailMinWidth: paneAwareDetailMinWidth
        )
    }

    var shellWindowMinWidth: Double {
        Self.shellWindowMinWidth(
            windowWidth: measuredWindowWidth,
            horizontalSizeClass: horizontalSizeClass,
            sidebarVisible: showSidebar,
            inspectorVisible: showInspectorSidebar,
            detailMinWidth: paneAwareDetailMinWidth
        )
    }

    static func windowMinWidth(
        sidebarVisible: Bool,
        inspectorVisible: Bool,
        detailMinWidth: Double
    ) -> Double {
        #if os(macOS)
        let sidebarMinWidth = sidebarVisible ? ContentView.sidebarMinWidth : 0
        // The inspector's OWN .inspectorColumnWidth enforces its column width
        // internally, but the inspector width must ALSO be included in the
        // window-level minimum. Without it, a narrow window (e.g. 400 px) gives
        // the NavigationSplitView only 150 px after the inspector takes 250 px —
        // less than sidebar + content need — causing the split view to switch to
        // overlay mode and float the sidebar OVER the library content (#2309).
        let inspectorMinWidth = inspectorVisible ? ContentView.inspectorMinWidth : 0
        return sidebarMinWidth + detailMinWidth + inspectorMinWidth
        #else
        return detailMinWidth
        #endif
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
            let firstSelectedId = browserSelection.first
            if let firstSelectedId {
                detailDocument = documentStore.currentDocuments.first(where: { $0.id == firstSelectedId })
            }
        }
        recordNavigationEntry()
    }

    /// Normalize a requested display mode against current feature gates.
    func normalizedViewDisplayMode(_ mode: ViewDisplayMode) -> ViewDisplayMode {
        // Legacy rawValue migration ("Map"/"Spatial"→.canvas, "RealityKit"→.space)
        // now happens in ViewDisplayMode.init?(rawValue:) at decode time (#3081),
        // so here we only fall back when the requested mode isn't available in the
        // current context (e.g. .space before its renderer is offered, #3081).
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

    /// Handles `.onChange(of: sidebarSelectionState.selectedItemId)` — the single
    /// runtime source (#3036). @SceneStorage `selectedSidebarItemId` is now purely
    /// a persistence adapter (restore-once + write-through), not a second source.
    /// Restores per-folder view mode and drives the inspector from sidebar selection.
    func handleSidebarSelectionChange(_ newFolderId: String?) {
        if isRestoringNavigationHistory { return }
        if newFolderId == "entities-browser" {
            viewDisplayMode = .list
            browserSelection.removeAll()
            detailDocument = nil
            kgFocusState.clear()
            return
        }
        kgFocusState.clear()
        // Restore per-folder view mode when switching folders.
        // Priority: per-folder save > per-scene @SceneStorage value > global default.
        // The @SceneStorage value holds the user's last choice for this window/tab
        // and should win for new or unsaved folders so spatial is not forced (#2311).
        if let saved = displayMode(for: newFolderId) {
            viewDisplayMode = normalizedViewDisplayMode(saved)
        } else {
            let normalizedSceneValue = normalizedViewDisplayMode(viewDisplayMode)
            let normalizedDefault = normalizedViewDisplayMode(defaultLibraryViewDisplayMode)
            // If the scene value is unset or unavailable for this context, fall
            // back to the global default rather than forcing a spatial/canvas mode.
            if normalizedSceneValue != normalizedDefault {
                viewDisplayMode = normalizedSceneValue
            } else if viewDisplayMode != normalizedDefault {
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
                    let fetched = try? await documentStore.documentService.getDocument(docId)
                    if let fetched, sidebarSelectionState.selectedItemId == prefixedId {
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
        case .canvas, .space, .workspace: .canvas
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
        if horizontalSizeClass == .compact || shouldUseRuntimeSidebarCollapse {
            return
        }

        // Persist column visibility to @SceneStorage
        // Map NavigationSplitViewVisibility to raw int for @SceneStorage
        columnVisibilityRaw = Self.persistedColumnVisibilityRaw(for: newVisibility)

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
        if isEntityLibrarySelection {
            guard let firstId = newSelection.first else {
                kgFocusState.clear()
                detailDocument = nil
                return
            }
            kgFocusState.focusEntity(entityId: firstId)
            detailDocument = nil
            return
        }
        if kgFocusState.focusedEntityId != nil {
            kgFocusState.clear()
        }
        guard let firstId = newSelection.first,
              let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }),
              BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: currentLayoutMode,
                selectedDocumentId: firstId,
                currentDetailDocumentId: detailDocument?.id
              ) else {
            if newSelection.isEmpty {
                detailDocument = nil
            }
            return
        }
        detailDocument = doc
    }

    /// Handles `.onChange(of: detailDocument)`.
    /// Keeps documentStore.selectedDocument in sync and records navigation.
    func handleDetailDocumentChange(_ newDoc: Document?) {
        // Keep documentStore.selectedDocument in sync so WorkflowEditor
        // toolbar button sees the current document at run time.
        documentStore.selectedDocument = newDoc
        // Clear page focus so the inspector starts fresh on the new container
        // rather than showing a page from the previous document (#1463).
        pageFocusDocument = nil
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

    /// Handles `.onReceive` of `.ficheroSelectDocumentRequested`.
    /// AppleScript command path for `select document id "..."`.
    func handleAppleScriptSelectDocument(_ note: Notification) {
        guard let documentId = note.userInfo?["id"] as? String,
              !documentId.isEmpty else { return }
        sidebarMode = .library
        showSidebar = true
        showInspectorSidebar = true
        focusedPane = .inspector
        browserSelection = [documentId]
        sidebarSelectionState.selectedItemId = "doc:\(documentId)"
    }

    /// Handles `.onReceive` of `.ficheroShowPanelRequested`.
    /// AppleScript command path for `show panel "library|inspector|kg|activity"`.
    func handleAppleScriptShowPanel(_ note: Notification) {
        guard let rawPanel = note.userInfo?["panel"] as? String else { return }
        switch rawPanel.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "library":
            sidebarMode = .library
            showSidebar = true
            focusedPane = .content
        case "inspector":
            showInspectorSidebar = true
            focusedPane = .inspector
        case "kg", "knowledge graph", "knowledge-graph":
            sidebarMode = .knowledgeGraph
            showSidebar = true
            sidebarSelectionState.selectedItemId = "entities-browser"
            focusedPane = .content
        case "activity":
            sidebarMode = .activity
            showSidebar = true
            sidebarSelectionState.selectedItemId = "activity-browser"
            focusedPane = .content
        default:
            return
        }
    }
}
