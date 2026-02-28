import Foundation

// MARK: - Request Types

/// Request model for creating a document.
struct DocumentCreateRequest: Codable {
    let name: String
    var parentId: String?
    var docType: DocType = .file
    var fileType: FileType?
    var path: String?
    var pageContent: String?
    var metadata: [String: AnyCodable] = [:]

    enum CodingKeys: String, CodingKey {
        case name
        case parentId = "parent_id"
        case docType = "doc_type"
        case fileType = "file_type"
        case path
        case pageContent = "page_content"
        case metadata
    }
}

/// Request model for updating a document.
struct DocumentUpdateRequest: Codable {
    var name: String?
    var parentId: String?
    var docType: DocType?
    var fileType: FileType?
    var path: String?
    var pageContent: String?
    var status: Status?
    var metadata: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case name
        case parentId = "parent_id"
        case docType = "doc_type"
        case fileType = "file_type"
        case path
        case pageContent = "page_content"
        case status
        case metadata
    }
}

// MARK: - Helper Types

/// Represents a document with its context in the hierarchy.
struct DocumentHierarchy {
    let ancestors: [Document]  // Sorted from root to immediate parent
    let document: Document
    let children: [Document]

    /// The immediate parent, if any.
    var parent: Document? {
        ancestors.last
    }

    /// Breadcrumb path from root to this document.
    var breadcrumb: [Document] {
        ancestors + [document]
    }
}

// MARK: - Document Store Errors

/// Errors specific to DocumentStore operations
enum DocumentStoreError: Error, LocalizedError {
    case fileNotFound(String)
    case fileNotReadable(String)
    case invalidFilename
    case invalidParentId
    case invalidResponse
    case badRequest
    case unauthorized
    case notFound
    case fileTooLarge
    case serverError(Int)

    var errorDescription: String? {
        switch self {
        case .fileNotFound(let path):
            return "File not found: \(path)"
        case .fileNotReadable(let path):
            return "Cannot read file: \(path)"
        case .invalidFilename:
            return "Invalid or empty filename"
        case .invalidParentId:
            return "Invalid parent folder ID"
        case .invalidResponse:
            return "Invalid server response"
        case .badRequest:
            return "Invalid request"
        case .unauthorized:
            return "Unauthorized access"
        case .notFound:
            return "Resource not found"
        case .fileTooLarge:
            return "File is too large to upload"
        case .serverError(let code):
            return "Server error (HTTP \(code))"
        }
    }
}
