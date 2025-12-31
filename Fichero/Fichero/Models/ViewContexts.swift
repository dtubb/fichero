import Foundation
import SwiftUI

// MARK: - Library Context

/// Context for Library view tab
struct LibraryContext: Codable {
    /// Currently selected collection ID (nil = root)
    var selectedCollectionId: String?

    /// Selected document IDs
    var selectedDocumentIds: Set<String>

    /// View layout preference
    var viewLayout: LibraryLayout

    /// Show inspector
    var showInspector: Bool

    init(
        selectedCollectionId: String? = nil,
        selectedDocumentIds: Set<String> = [],
        viewLayout: LibraryLayout = .icons,
        showInspector: Bool = true
    ) {
        self.selectedCollectionId = selectedCollectionId
        self.selectedDocumentIds = selectedDocumentIds
        self.viewLayout = viewLayout
        self.showInspector = showInspector
    }
}

// MARK: - Workflow Context

/// Context for Workflow view tab
struct WorkflowContext: Codable {
    /// Workflow ID being edited
    var workflowId: String?

    /// Canvas position (for panning)
    var canvasPosition: CGPoint

    /// Zoom level
    var zoom: CGFloat

    /// Selected node IDs
    var selectedNodeIds: Set<String>

    /// Show inspector
    var showInspector: Bool

    init(
        workflowId: String? = nil,
        canvasPosition: CGPoint = .zero,
        zoom: CGFloat = 1.0,
        selectedNodeIds: Set<String> = [],
        showInspector: Bool = true
    ) {
        self.workflowId = workflowId
        self.canvasPosition = canvasPosition
        self.zoom = zoom
        self.selectedNodeIds = selectedNodeIds
        self.showInspector = showInspector
    }

    // Custom Codable implementation for CGPoint
    enum CodingKeys: String, CodingKey {
        case workflowId
        case canvasPositionX
        case canvasPositionY
        case zoom
        case selectedNodeIds
        case showInspector
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        workflowId = try container.decodeIfPresent(String.self, forKey: .workflowId)
        let x = try container.decode(Double.self, forKey: .canvasPositionX)
        let y = try container.decode(Double.self, forKey: .canvasPositionY)
        canvasPosition = CGPoint(x: x, y: y)
        zoom = try container.decode(CGFloat.self, forKey: .zoom)
        selectedNodeIds = try container.decode(Set<String>.self, forKey: .selectedNodeIds)
        showInspector = try container.decode(Bool.self, forKey: .showInspector)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(workflowId, forKey: .workflowId)
        try container.encode(canvasPosition.x, forKey: .canvasPositionX)
        try container.encode(canvasPosition.y, forKey: .canvasPositionY)
        try container.encode(zoom, forKey: .zoom)
        try container.encode(selectedNodeIds, forKey: .selectedNodeIds)
        try container.encode(showInspector, forKey: .showInspector)
    }
}

// MARK: - Chat Context

/// Context for Chat view tab
struct ChatContext: Codable {
    /// Conversation ID
    var conversationId: String?

    /// Selected documents for context
    var selectedDocuments: Set<String>

    /// Show inspector
    var showInspector: Bool

    /// Current provider
    var selectedProvider: String?

    /// Current model
    var selectedModel: String?

    init(
        conversationId: String? = nil,
        selectedDocuments: Set<String> = [],
        showInspector: Bool = true,
        selectedProvider: String? = nil,
        selectedModel: String? = nil
    ) {
        self.conversationId = conversationId
        self.selectedDocuments = selectedDocuments
        self.showInspector = showInspector
        self.selectedProvider = selectedProvider
        self.selectedModel = selectedModel
    }
}

// MARK: - Search Context

/// Context for Search view tab
struct SearchContext: Codable {
    /// Current search query
    var query: String

    /// Selected saved search ID
    var savedSearchId: String?

    /// Search results (not saved, just for session)
    var lastSearchQuery: String?

    /// Show inspector
    var showInspector: Bool

    init(
        query: String = "",
        savedSearchId: String? = nil,
        lastSearchQuery: String? = nil,
        showInspector: Bool = true
    ) {
        self.query = query
        self.savedSearchId = savedSearchId
        self.lastSearchQuery = lastSearchQuery
        self.showInspector = showInspector
    }
}
