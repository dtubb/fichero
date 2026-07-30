import Foundation
import Observation

/// Category for grouping item types in menus
enum ItemMenuCategory: String, CaseIterable {
    case documents = "Documents"
    case aiTools = "AI"
    case automation = "Automation"
    case places = "Places"
    case tools = "Tools"
}

/// Definition of a creatable item type
struct ItemTypeDefinition: Identifiable {
    let id: String
    let name: String
    let icon: String
    let menuCategory: ItemMenuCategory
    let keyboardShortcut: String?
    let handler: () -> Void

    init(
        id: String,
        name: String,
        icon: String,
        category: ItemMenuCategory,
        keyboardShortcut: String? = nil,
        handler: @escaping () -> Void
    ) {
        self.id = id
        self.name = name
        self.icon = icon
        self.menuCategory = category
        self.keyboardShortcut = keyboardShortcut
        self.handler = handler
    }
}

/// Registry of all creatable item types
/// Provides a single source of truth for what can be created in the app
@MainActor
@Observable
class ItemTypeRegistry {
    // Handlers injected from SidebarView (have access to services)
    var createFolder: (() -> Void)?
    var importFiles: (() -> Void)?
    var createChat: (() -> Void)?
    /// New saved agent workspace (#4308/#4335): a workspace node in the
    /// current library that opens the Research surface.
    var createWorkspace: (() -> Void)?
    var createComparison: (() -> Void)?
    var createWorkflow: (() -> Void)?
    var createChain: (() -> Void)?
    var createSchedule: (() -> Void)?
    var createTrigger: (() -> Void)?

    // Future handlers (to be implemented)
    var createAgent: (() -> Void)?
    var createAction: (() -> Void)?
    var createAutomation: (() -> Void)?
    var createPlace: (() -> Void)?
    var createApp: (() -> Void)?

    /// All registered item types
    var definitions: [ItemTypeDefinition] {
        var items: [ItemTypeDefinition] = []

        // Documents category
        if let handler = createFolder {
            items.append(ItemTypeDefinition(
                id: "folder",
                name: "Folder",
                icon: "folder.badge.plus",
                category: .documents,
                keyboardShortcut: "n",
                handler: handler
            ))
        }

        if let handler = importFiles {
            items.append(ItemTypeDefinition(
                id: "import",
                name: "Import Files...",
                icon: "square.and.arrow.down",
                category: .documents,
                keyboardShortcut: "i",
                handler: handler
            ))
        }

        // AI category
        if let handler = createChat {
            items.append(ItemTypeDefinition(
                id: "chat",
                name: "Chat",
                icon: "message.circle",
                category: .aiTools,
                keyboardShortcut: "t",
                handler: handler
            ))
        }

        if let handler = createWorkspace {
            items.append(ItemTypeDefinition(
                id: "workspace",
                name: "Workspace",
                icon: "square.grid.2x2",
                category: .aiTools,
                handler: handler
            ))
        }

        if let handler = createComparison {
            items.append(ItemTypeDefinition(
                id: "comparison",
                name: "Comparison",
                icon: "arrow.left.arrow.right",
                category: .aiTools,
                handler: handler
            ))
        }

        if let handler = createWorkflow {
            items.append(ItemTypeDefinition(
                id: "workflow",
                name: "Workflow",
                icon: "flowchart",
                category: .aiTools,
                keyboardShortcut: "w",
                handler: handler
            ))
        }

        if let handler = createChain {
            items.append(ItemTypeDefinition(
                id: "chain",
                name: "Chain",
                icon: "link",
                category: .aiTools,
                handler: handler
            ))
        }

        // Automation category
        if let handler = createSchedule {
            items.append(ItemTypeDefinition(
                id: "schedule",
                name: "Schedule",
                icon: "calendar.badge.clock",
                category: .automation,
                handler: handler
            ))
        }

        if let handler = createTrigger {
            items.append(ItemTypeDefinition(
                id: "trigger",
                name: "Trigger",
                icon: "bolt.badge.automatic",
                category: .automation,
                handler: handler
            ))
        }

        if let handler = createAutomation {
            items.append(ItemTypeDefinition(
                id: "automation",
                name: "Automation",
                icon: "gearshape.2",
                category: .automation,
                handler: handler
            ))
        }

        if let handler = createAction {
            items.append(ItemTypeDefinition(
                id: "action",
                name: "Action",
                icon: "bolt.circle",
                category: .automation,
                handler: handler
            ))
        }

        // Places category (future)
        if let handler = createPlace {
            items.append(ItemTypeDefinition(
                id: "place",
                name: "Place",
                icon: "location.circle",
                category: .places,
                handler: handler
            ))
        }

        // Tools category (future)
        if let handler = createApp {
            items.append(ItemTypeDefinition(
                id: "app",
                name: "App Integration",
                icon: "app.badge",
                category: .tools,
                handler: handler
            ))
        }

        return items
    }

    /// Get definitions grouped by category
    var definitionsByCategory: [ItemMenuCategory: [ItemTypeDefinition]] {
        Dictionary(grouping: definitions, by: { $0.menuCategory })
    }

    /// Get definition by ID
    func definition(for id: String) -> ItemTypeDefinition? {
        definitions.first { $0.id == id }
    }
}
