import Observation
import SwiftUI

enum SidebarBrowserDestination: String, Hashable {
    case activity
    case workflows
    case batches
    case entities
    case comparison
    case research
}

enum SidebarDestination: Hashable {
    case document(String)
    case search(String)
    case chat(String)
    case workflow(String)
    case chain(String)
    case schedule(String)
    case trigger(String)
    case batch(String)
    case run(String)
    case structure(documentId: String, nodeId: String)
    case browser(SidebarBrowserDestination)
    case library(UUID)

    init?(serializedID: String) {
        switch serializedID {
        case "activity-browser": self = .browser(.activity)
        case "workflows-browser": self = .browser(.workflows)
        case "batches-browser": self = .browser(.batches)
        case "entities-browser": self = .browser(.entities)
        case "comparison-browser": self = .browser(.comparison)
        case "research-browser": self = .browser(.research)
        default:
            if let id = serializedID.stripPrefix("doc:") {
                self = .document(id)
            } else if let id = serializedID.stripPrefix("search:") {
                self = .search(id)
            } else if let id = serializedID.stripPrefix("chat:") {
                self = .chat(id)
            } else if let id = serializedID.stripPrefix("workflow:") {
                self = .workflow(id)
            } else if let id = serializedID.stripPrefix("chain:") {
                self = .chain(id)
            } else if let id = serializedID.stripPrefix("schedule:") {
                self = .schedule(id)
            } else if let id = serializedID.stripPrefix("trigger:") {
                self = .trigger(id)
            } else if let id = serializedID.stripPrefix("batch:") {
                self = .batch(id)
            } else if let id = serializedID.stripPrefix("run:") {
                self = .run(id)
            } else if let payload = serializedID.stripPrefix("structure:") {
                let parts = payload.split(separator: ":", maxSplits: 1).map(String.init)
                guard parts.count == 2 else { return nil }
                self = .structure(documentId: parts[0], nodeId: parts[1])
            } else if let id = serializedID.stripPrefix("library:"),
                      let uuid = UUID(uuidString: id) {
                self = .library(uuid)
            } else {
                return nil
            }
        }
    }

    var serializedID: String {
        switch self {
        case .document(let id): return "doc:\(id)"
        case .search(let id): return "search:\(id)"
        case .chat(let id): return "chat:\(id)"
        case .workflow(let id): return "workflow:\(id)"
        case .chain(let id): return "chain:\(id)"
        case .schedule(let id): return "schedule:\(id)"
        case .trigger(let id): return "trigger:\(id)"
        case .batch(let id): return "batch:\(id)"
        case .run(let id): return "run:\(id)"
        case .structure(let documentId, let nodeId): return "structure:\(documentId):\(nodeId)"
        case .browser(.activity): return "activity-browser"
        case .browser(.workflows): return "workflows-browser"
        case .browser(.batches): return "batches-browser"
        case .browser(.entities): return "entities-browser"
        case .browser(.comparison): return "comparison-browser"
        case .browser(.research): return "research-browser"
        case .library(let id): return "library:\(id.uuidString)"
        }
    }
}

private extension String {
    func stripPrefix(_ prefix: String) -> String? {
        hasPrefix(prefix) ? String(dropFirst(prefix.count)) : nil
    }
}

/// Manages rename state for sidebar items.
/// Use @State in parent view, pass as @Bindable to children.
@MainActor
@Observable
class RenameStateManager {
    var renamingItemId: String?
    var editingName: String = ""

    func startRename(itemId: String, currentName: String) {
        renamingItemId = itemId
        editingName = currentName
    }

    func cancelRename() {
        renamingItemId = nil
        editingName = ""
    }
}

/// Manages delete confirmation state for sidebar items.
/// Use @State in parent view, pass as @Bindable to children.
@MainActor
@Observable
class DeleteStateManager {
    var showingDeleteConfirmation = false
    var showingDeleteError = false
    var itemToDelete: SidebarItem?
    var deleteErrorMessage = ""

    func showDeleteConfirmation(for item: SidebarItem) {
        itemToDelete = item
        showingDeleteConfirmation = true
    }

    func cancelDelete() {
        showingDeleteConfirmation = false
        showingDeleteError = false
        itemToDelete = nil
        deleteErrorMessage = ""
    }

    func showError(message: String) {
        deleteErrorMessage = message
        showingDeleteError = true
        showingDeleteConfirmation = false
    }
}

/// Shared live selection for the sidebar tree.
/// Keep this as the single runtime source of truth so the List selection,
/// row taps, and content routing all observe the same value.
@MainActor
@Observable
class SidebarSelectionState {
    var selectedDestination: SidebarDestination?

    var selectedItemId: String? {
        get { selectedDestination?.serializedID }
        set {
            selectedDestination = newValue.flatMap(SidebarDestination.init(serializedID:))
        }
    }
}
