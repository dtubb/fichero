import SwiftUI
import OSLog

// MARK: - ContentView Persistence Extension
// Agent: PersistenceAgent
// Responsibility: State serialization/deserialization for @SceneStorage

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ContentView")

extension ContentView {
    
    // MARK: - State Restoration
    
    func restoreViewMode(type: String, itemId: String?) -> AppViewMode {
        switch type {
        case "library":
            guard let id = itemId else { return .library(nil) }
            let doc = documentStore.collections.first { $0.id == id }
            return .library(doc)

        case "search":
            guard let id = itemId else { return .search(nil) }
            let search = savedSearchService.savedSearches.first { $0.id == id }
            return .search(search)

        case "chat":
            guard let id = itemId else { return .chat(nil) }
            let conversation = conversationService.conversations.first { $0.id == id }
            return .chat(conversation)

        case "comparison":
            return .comparison(nil)

        case "workflow":
            guard let id = itemId else { return .workflow(nil) }
            let workflow = workflowStore.workflows.first { $0.id == id }
            return .workflow(workflow)

        case "chain":
            return .chain(nil)

        case "batches":
            return .batches

        case "batch":
            return .batches

        case "automation":
            return .automation

        case "schedule":
            return .automation

        case "trigger":
            return .automation

        case "activity":
            // Activity runs are loaded dynamically when the view appears
            // For now, return nil and let the view populate it
            return .activity(nil)

        default:
            return .library(nil)
        }
    }

    func serializeViewMode(_ mode: AppViewMode) -> (type: String, id: String?) {
        switch mode {
        case .library(let doc):
            return ("library", doc?.id)
        case .search(let search):
            return ("search", search?.id)
        case .chat(let conversation):
            return ("chat", conversation?.id)
        case .comparison(let comparison):
            return ("comparison", comparison.map { $0.comparisonId })
        case .workflow(let workflow):
            return ("workflow", workflow?.id)
        case .chain(let chain):
            return ("chain", chain?.id)
        case .batches:
            return ("batches", nil)
        case .batch(let batch):
            return ("batch", batch?.batchId)
        case .automation:
            return ("automation", nil)
        case .schedule(let schedule):
            return ("schedule", schedule.map { $0.scheduleId })
        case .trigger(let trigger):
            return ("trigger", trigger.map { $0.triggerId })
        case .activity(let run):
            return ("activity", run?.id)
        }
    }

    func restorePersistedState() {
        columnVisibility = {
            switch columnVisibilityRaw {
            case 0: return .automatic
            case 1: return .detailOnly
            case 2: return .all
            case 3: return .doubleColumn
            default: return .all
            }
        }()

        if let decodedSelection = try? JSONDecoder().decode(Set<String>.self, from: browserSelectionData) {
            browserSelection = decodedSelection
        }

        viewMode = restoreViewMode(type: storedViewModeType, itemId: storedViewModeItemId)

        logger.info("""
            Restored persisted state: viewMode=\(storedViewModeType), \
            selectedItem=\(selectedSidebarItemId ?? "nil")
            """)
    }

    func savePersistedState() {
        // Map NavigationSplitViewVisibility to raw integer for @SceneStorage
        if columnVisibility == .automatic {
            columnVisibilityRaw = 0
        } else if columnVisibility == .detailOnly {
            columnVisibilityRaw = 1
        } else if columnVisibility == .all {
            columnVisibilityRaw = 2
        } else if columnVisibility == .doubleColumn {
            columnVisibilityRaw = 3
        } else {
            columnVisibilityRaw = 0
        }

        if let encoded = try? JSONEncoder().encode(browserSelection) {
            browserSelectionData = encoded
        }

        let (type, id) = serializeViewMode(viewMode)
        storedViewModeType = type
        storedViewModeItemId = id
    }
}
