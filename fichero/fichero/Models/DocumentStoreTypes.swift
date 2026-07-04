import Foundation

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
