import Foundation

// MARK: - Models

struct AppIntegration: Codable, Identifiable, Hashable {
    let name: String
    let bundleId: String
    let status: String
    let version: String?
    let path: String?
    let error: String?

    var id: String { name }

    var isAvailable: Bool {
        status == "available"
    }

    enum CodingKeys: String, CodingKey {
        case name
        case bundleId = "bundle_id"
        case status
        case version
        case path
        case error
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(name)
    }

    static func == (lhs: AppIntegration, rhs: AppIntegration) -> Bool {
        lhs.name == rhs.name
    }
}

struct IntegrationItem: Codable, Identifiable {
    let externalId: String
    let name: String
    let sourceApp: String
    let itemType: String
    let filePath: String?
    let url: String?
    let content: String?
    let metadata: [String: String]
    let createdAt: String?
    let modifiedAt: String?

    var id: String { externalId }

    enum CodingKeys: String, CodingKey {
        case externalId = "external_id"
        case name
        case sourceApp = "source_app"
        case itemType = "item_type"
        case filePath = "file_path"
        case url
        case content
        case metadata
        case createdAt = "created_at"
        case modifiedAt = "modified_at"
    }
}

struct ImportResult: Codable {
    let success: Bool
    let filePath: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case filePath = "file_path"
        case error
    }
}

struct ExportResult: Codable {
    let success: Bool
    let externalId: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case externalId = "external_id"
        case error
    }
}

struct DEVONthinkDatabase: Codable, Identifiable {
    let name: String
    let uuid: String?
    let path: String?

    var id: String { uuid ?? name }
}

struct BookendsLibrary: Codable, Identifiable {
    let name: String
    let path: String?

    var id: String { path ?? name }
}

struct TinderboxDocument: Codable, Identifiable {
    let name: String
    let path: String?

    var id: String { path ?? name }
}

// MARK: - Errors

enum IntegrationsError: LocalizedError {
    case invalidURL
    case serverError
    case appNotAvailable(String)
    case createFailed

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .serverError:
            return "Server error"
        case .appNotAvailable(let app):
            return "\(app) is not available"
        case .createFailed:
            return "Failed to create item"
        }
    }
}
