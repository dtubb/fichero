import Foundation

// MARK: - Research display models (mirrors backend research_models.py)

enum ResearchProjectStatus: String, Codable, CaseIterable {
    case active, paused, completed, archived
    var label: String { rawValue.capitalized }
}

enum ResearchPlanStatus: String, Codable, CaseIterable {
    case draft, active, completed, cancelled
    var label: String { rawValue.capitalized }
}

enum ResearchTaskStatus: String, Codable, CaseIterable {
    case pending, inProgress, completed, blocked, cancelled

    var rawValueForAPI: String {
        switch self {
        case .inProgress: return "in_progress"
        default: return rawValue
        }
    }

    var label: String {
        switch self {
        case .inProgress: return "In Progress"
        default: return rawValue.capitalized
        }
    }

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        switch raw {
        case "in_progress": self = .inProgress
        case "pending": self = .pending
        case "completed": self = .completed
        case "blocked": self = .blocked
        case "cancelled": self = .cancelled
        default: self = .pending
        }
    }
}

struct ResearchProject: Codable, Identifiable, Hashable {
    let id: String
    var name: String
    var description: String
    var status: ResearchProjectStatus
    var libraryDestinationFolderId: String?
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, description, status
        case libraryDestinationFolderId = "library_destination_folder_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ResearchPlan: Codable, Identifiable, Hashable {
    let id: String
    var projectId: String
    var name: String
    var description: String
    var status: ResearchPlanStatus
    var orderIndex: Int
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, description, status
        case projectId = "project_id"
        case orderIndex = "order_index"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ResearchTask: Codable, Identifiable, Hashable {
    let id: String
    var planId: String
    var name: String
    var description: String
    var status: ResearchTaskStatus
    var priority: Int
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, description, status, priority
        case planId = "plan_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ResearchNote: Codable, Identifiable, Hashable {
    let id: String
    var projectId: String
    var taskId: String?
    var noteType: String
    var content: String
    var tags: [String]
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, content, tags
        case projectId = "project_id"
        case taskId = "task_id"
        case noteType = "note_type"
        case createdAt = "created_at"
    }
}

struct ResearchSource: Codable, Identifiable, Hashable {
    let id: String
    var projectId: String
    var sourceType: String
    var label: String
    var url: String?
    var description: String
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, label, url, description
        case projectId = "project_id"
        case sourceType = "source_type"
        case createdAt = "created_at"
    }
}

// MARK: - Request / Response types for browser-save

struct BrowserSaveRequest: Codable {
    var url: String
    var projectId: String
    var suggestedName: String?
    var parentFolderId: String?

    enum CodingKeys: String, CodingKey {
        case url
        case projectId = "project_id"
        case suggestedName = "suggested_name"
        case parentFolderId = "parent_folder_id"
    }
}

struct BrowserSaveResponse: Codable {
    var documentId: String?
    var documentName: String?
    var filePath: String?
    var contentType: String?
    var sizeBytes: Int?
    var success: Bool
    var error: String?

    enum CodingKeys: String, CodingKey {
        case success, error
        case documentId = "document_id"
        case documentName = "document_name"
        case filePath = "file_path"
        case contentType = "content_type"
        case sizeBytes = "size_bytes"
    }
}
