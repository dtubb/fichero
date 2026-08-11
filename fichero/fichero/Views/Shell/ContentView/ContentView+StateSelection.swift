import SwiftUI

// MARK: - ContentView Selection & Visibility State

extension ContentView {

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
        // Document-order primary, never Set.first (F3, 2026-08-09): the
        // inspector must name the SAME member of a multi-selection as the
        // preview and detail — a hash-order draw here is 'the inspector
        // shows another page'.
        if let firstId = shellPrimarySelectionId(
               in: browserSelection, orderedBy: documentStore.currentDocuments
           ),
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
        case .library, .chat, .comparison, .workflow, .chain:
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
        case .library, .workflows:
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
}
