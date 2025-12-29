import SwiftUI

/// Environment key for sidebar services.
/// This follows Apple's pattern of using @EnvironmentObject for shared state
/// instead of passing multiple parameters through view hierarchies.
///
/// Example from Apple's Food Truck sample:
/// ```swift
/// @EnvironmentObject private var model: Model
/// ```
struct SidebarServicesKey: EnvironmentKey {
    static let defaultValue = SidebarServices()
}

extension EnvironmentValues {
    var sidebarServices: SidebarServices {
        get { self[SidebarServicesKey.self] }
        set { self[SidebarServicesKey.self] = newValue }
    }
}

/// Container for all sidebar-related services.
/// Reduces the 9-parameter problem in SidebarItemRow to a single environment object.
@MainActor
class SidebarServices: ObservableObject {
    var documentStore: DocumentStore?
    var savedSearchService: SavedSearchService?
    var conversationService: ConversationService?
    var workflowStore: WorkflowStore?

    nonisolated init(
        documentStore: DocumentStore? = nil,
        savedSearchService: SavedSearchService? = nil,
        conversationService: ConversationService? = nil,
        workflowStore: WorkflowStore? = nil
    ) {
        self.documentStore = documentStore
        self.savedSearchService = savedSearchService
        self.conversationService = conversationService
        self.workflowStore = workflowStore
    }
}
