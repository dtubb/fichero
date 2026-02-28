import Foundation

// MARK: - Conversation (for RAG Chat)

struct Conversation: Identifiable, Codable, Hashable {
    let id: String
    var title: String
    var messages: [ChatMessage]
    var documentScope: [String]  // Document IDs to search within
    var folderPath: String
    var sortOrder: Int
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case messages
        case documentScope = "document_ids"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(
        id: String = UUID().uuidString,
        title: String = "New Chat",
        messages: [ChatMessage] = [],
        documentScope: [String] = [],
        folderPath: String = "/",
        sortOrder: Int = 0,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.messages = messages
        self.documentScope = documentScope
        self.folderPath = folderPath
        self.sortOrder = sortOrder
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

struct ChatMessage: Identifiable, Codable, Hashable {
    let id: String
    var role: ChatRole
    var content: String
    var sources: [DocumentSource]?
    var timestamp: Date

    init(
        id: String = UUID().uuidString,
        role: ChatRole,
        content: String,
        sources: [DocumentSource]? = nil,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.sources = sources
        self.timestamp = timestamp
    }
}

enum ChatRole: String, Codable, Hashable {
    case user
    case assistant
    case system
}

struct DocumentSource: Identifiable, Codable, Hashable {
    let id: String
    let documentId: String
    let documentName: String
    let excerpt: String
    let relevanceScore: Double
}
