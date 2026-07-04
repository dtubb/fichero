import OSLog
import SwiftUI

// MARK: - ContentView Persistence Extension
// Agent: PersistenceAgent
// Responsibility: State serialization/deserialization for @SceneStorage

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")

extension ContentView {

    static func restoredColumnVisibility(from rawValue: Int) -> NavigationSplitViewVisibility {
        switch rawValue {
        case 0:
            return .automatic
        case 1:
            return .detailOnly
        case 2:
            #if os(macOS)
            return .all
            #else
            return .detailOnly
            #endif
        case 3:
            return .doubleColumn
        default:
            #if os(macOS)
            return .all
            #else
            return .detailOnly
            #endif
        }
    }

    static func persistedColumnVisibilityRaw(for visibility: NavigationSplitViewVisibility) -> Int {
        if visibility == .automatic {
            return 0
        } else if visibility == .detailOnly {
            return 1
        } else if visibility == .all {
            #if os(macOS)
            return 2
            #else
            return 3
            #endif
        } else if visibility == .doubleColumn {
            return 3
        } else {
            #if os(macOS)
            return 2
            #else
            return 1
            #endif
        }
    }

    // MARK: - State Restoration

    // swiftlint:disable:next cyclomatic_complexity
    func restoreViewMode(type: String, itemId: String?) -> AppViewMode {
        switch type {
        case "library":
            guard let id = normalizedStoredItemId(for: type, rawItemId: itemId) else {
                return .library(nil)
            }
            let doc = documentStore.collections.first { $0.id == id }
            return .library(doc)

        case "search":
            guard let id = normalizedStoredItemId(for: type, rawItemId: itemId) else {
                return .search(nil)
            }
            let search = savedSearchService.savedSearches.first { $0.id == id }
            return .search(search)

        case "chat":
            guard let id = normalizedStoredItemId(for: type, rawItemId: itemId) else {
                return .chat(nil)
            }
            let conversation = conversationService.conversations.first { $0.id == id }
            return .chat(conversation)

        case "comparison":
            return .comparison(nil)

        case "workflow":
            guard let id = normalizedStoredItemId(for: type, rawItemId: itemId) else {
                return .workflow(nil)
            }
            let workflow = workflowStore.workflows.first { $0.id == id }
            return .workflow(workflow)

        case "chain":
            return .chain(nil)

        case "batches", "batch":
            return .activity(nil)

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

    // swiftlint:disable cyclomatic_complexity
    /// Pure `AppViewMode` → persisted `(type, id)` mapping. Static so the save
    /// contract (what iOS scene-background / macOS terminate flush) is unit-
    /// testable without a live ContentView (#3016).
    static func serializeViewMode(_ mode: AppViewMode) -> (type: String, id: String?) {
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
        case .batches, .batch:
            return ("activity", nil)
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
    // swiftlint:enable cyclomatic_complexity

    func restorePersistedState() {
        columnVisibility = Self.restoredColumnVisibility(from: columnVisibilityRaw)
        // Derive explicit left-sidebar state from persisted split-view visibility.
        // In this app's layout, `.doubleColumn` means sidebar + content.
        showSidebar = columnVisibility != .detailOnly

        if let decodedSelection = try? JSONDecoder().decode(Set<String>.self, from: browserSelectionData) {
            browserSelection = decodedSelection
        }

        viewMode = restoreViewMode(type: storedViewModeType, itemId: storedViewModeItemId)
        if selectedSidebarItemId == nil {
            let restoredId = Self.sidebarSelectionId(
                for: storedViewModeType,
                itemId: storedViewModeItemId
            )
            selectedSidebarItemId = restoredId ?? (storedViewModeType == "activity" ? "activity-browser" : nil)
        }
        sidebarSelectionState.selectedItemId = selectedSidebarItemId

        logger.info("""
            Restored persisted state: viewMode=\(storedViewModeType), \
            selectedItem=\(selectedSidebarItemId ?? "nil")
            """)
    }

    // MARK: - Per-Folder Display Mode

    func displayMode(for folderId: String?) -> ViewDisplayMode? {
        guard let folderId else { return nil }
        guard let data = folderViewDisplayModesJSON.data(using: .utf8),
              let dict = try? JSONDecoder().decode([String: String].self, from: data),
              let rawValue = dict[folderId] else { return nil }
        return ViewDisplayMode(rawValue: rawValue)
    }

    func saveDisplayMode(_ mode: ViewDisplayMode, for folderId: String?) {
        guard let folderId else { return }
        guard let data = folderViewDisplayModesJSON.data(using: .utf8),
              var dict = try? JSONDecoder().decode([String: String].self, from: data) else { return }
        dict[folderId] = mode.rawValue
        if let encoded = try? JSONEncoder().encode(dict),
           let json = String(data: encoded, encoding: .utf8) {
            folderViewDisplayModesJSON = json
        }
    }

    func savePersistedState() {
        if horizontalSizeClass != .compact && !shouldUseRuntimeSidebarCollapse {
            // Map NavigationSplitViewVisibility to raw integer for @SceneStorage
            columnVisibilityRaw = Self.persistedColumnVisibilityRaw(for: columnVisibility)
        }

        if let encoded = try? JSONEncoder().encode(browserSelection) {
            browserSelectionData = encoded
        }

        let (type, id) = Self.serializeViewMode(viewMode)
        storedViewModeType = type
        storedViewModeItemId = id
        selectedSidebarItemId = sidebarSelectionState.selectedItemId ?? Self.sidebarSelectionId(for: type, itemId: id)
    }

    // MARK: - Sidebar Selection ID Mapping

    // swiftlint:disable:next cyclomatic_complexity
    static func sidebarSelectionId(for type: String, itemId: String?) -> String? {
        guard let itemId, !itemId.isEmpty else { return nil }
        switch type {
        case "library":
            return "doc:\(stripPrefix(itemId, prefix: "doc:"))"
        case "search":
            return "search:\(stripPrefix(itemId, prefix: "search:"))"
        case "chat":
            return "chat:\(stripPrefix(itemId, prefix: "chat:"))"
        case "workflow":
            return "workflow:\(stripPrefix(itemId, prefix: "workflow:"))"
        case "chain":
            return "chain:\(stripPrefix(itemId, prefix: "chain:"))"
        case "schedule":
            return "schedule:\(stripPrefix(itemId, prefix: "schedule:"))"
        case "trigger":
            return "trigger:\(stripPrefix(itemId, prefix: "trigger:"))"
        case "batch":
            return "batch:\(stripPrefix(itemId, prefix: "batch:"))"
        case "activity":
            return "activity:\(stripPrefix(itemId, prefix: "activity:"))"
        default:
            return itemId
        }
    }

    // swiftlint:disable:next cyclomatic_complexity
    func normalizedStoredItemId(for type: String, rawItemId: String?) -> String? {
        guard let rawItemId, !rawItemId.isEmpty else { return nil }
        switch type {
        case "library":
            return Self.stripPrefix(rawItemId, prefix: "doc:")
        case "search":
            return Self.stripPrefix(rawItemId, prefix: "search:")
        case "chat":
            return Self.stripPrefix(rawItemId, prefix: "chat:")
        case "workflow":
            return Self.stripPrefix(rawItemId, prefix: "workflow:")
        case "chain":
            return Self.stripPrefix(rawItemId, prefix: "chain:")
        case "schedule":
            return Self.stripPrefix(rawItemId, prefix: "schedule:")
        case "trigger":
            return Self.stripPrefix(rawItemId, prefix: "trigger:")
        case "batch":
            return Self.stripPrefix(rawItemId, prefix: "batch:")
        case "activity":
            return Self.stripPrefix(rawItemId, prefix: "activity:")
        default:
            return rawItemId
        }
    }

    private static func stripPrefix(_ value: String, prefix: String) -> String {
        if value.hasPrefix(prefix) {
            return String(value.dropFirst(prefix.count))
        }
        return value
    }
}
