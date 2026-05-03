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
        }

        return viewName
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
        // 2. Sidebar viewMode's folder doc.
        if let folder = currentSidebarFolder {
            return folder
        }
        // 3. Legacy fallback.
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
        case .chat, .automation, .activity:
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
            if !featureManager.isLibraryAdvancedViewsEnabled {
                return [.icon]
            }
            return ViewDisplayMode.allCases
        case .search:
            if !featureManager.isSearchAdvancedViewsEnabled {
                return [.list]
            }
            return ViewDisplayMode.allCases
        case .workflows:
            // 0.0.1: keep workflow presentation simple and explicit.
            // Icon = visual graph/canvas, List = ordered execution steps.
            return [.icon, .list]
        case .chat, .automation, .activity:
            return [.icon]
        }
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
        case .workflows, .automation, .activity:
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
}
