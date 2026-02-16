import SwiftUI
import OSLog

// MARK: - ContentView State Management Extension
// Agent: StateManagementAgent
// Responsibility: All @State, @SceneStorage, @EnvironmentObject properties and computed properties

extension ContentView {

    // MARK: - Computed Properties

    /// Toolbar title showing library name and current view
    var toolbarTitle: String {
        let libraryManager = LibraryManager.shared
        let libraryName: String

        if let currentId = libraryManager.currentLibraryId,
           let library = libraryManager.openLibraries.first(where: { $0.id == currentId }) {
            libraryName = library.displayName
        } else {
            libraryName = "Fichero"
        }

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

        return "\(libraryName) > \(viewName)"
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
        switch sidebarMode {
        case .library, .search, .chat:
            return true
        case .workflows, .automation, .batches, .activity:
            return false
        }
    }
}
