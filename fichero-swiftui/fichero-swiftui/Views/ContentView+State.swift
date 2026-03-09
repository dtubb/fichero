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
            viewName = "Batches"
        case .batch(let batch):
            viewName = batch.map { "Batch \(String($0.batchId.prefix(8)))" } ?? "Batch"
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

    /// Document to show in inspector
    var inspectorDocument: Document? {
        if let firstId = browserSelection.first {
            return documentStore.currentDocuments.first { $0.id == firstId }
        }
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

    /// Whether to show the inspector toggle button
    /// Only show for modes that have an inspector view
    var showInspectorToggle: Bool {
        switch viewMode {
        case .library, .search, .chat, .comparison, .workflow, .chain:
            return true
        case .batches, .batch, .automation, .schedule, .trigger, .activity:
            return false
        }
    }

    /// Whether to show the view mode picker (icon/list/table/map)
    /// Only makes sense for Library and Search modes
    var showViewModePicker: Bool {
        switch sidebarMode {
        case .library, .search:
            return true
        case .chat, .workflows, .automation, .batches, .activity:
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
        if sidebarMode == .library && !featureManager.isLibraryAdvancedViewsEnabled {
            return [.icon]
        }
        if sidebarMode == .search && !featureManager.isSearchAdvancedViewsEnabled {
            return [.list]
        }
        return ViewDisplayMode.allCases
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
    /// Library/Search split layouts are gated for 0.0.1.
    var availablePreviewModes: [PreviewMode] {
        switch sidebarMode {
        case .library, .search:
            if !featureManager.isLibrarySearchSplitLayoutsEnabled {
                return [.none]
            }
            return [.none, .standard, .widescreen]
        case .chat:
            return [.none, .standard, .widescreen]
        case .workflows, .automation, .batches, .activity:
            return []
        }
    }

    /// Normalize preview mode against current feature gates.
    func normalizedPreviewMode(_ mode: PreviewMode) -> PreviewMode {
        guard availablePreviewModes.contains(mode) else {
            if availablePreviewModes.contains(.none) {
                return .none
            }
            if availablePreviewModes.contains(.standard) {
                return .standard
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
