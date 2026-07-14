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
    case badRequest(detail: String? = nil)
    case unauthorized
    case notFound
    case fileTooLarge
    case serverError(Int, detail: String? = nil)

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
        case .badRequest(let detail):
            // Surface the engine's {"detail": ...} (#3802) — the reason the request was
            // rejected — falling back to the generic string only when there is no body.
            return detail ?? "Invalid request"
        case .unauthorized:
            return "Unauthorized access"
        case .notFound:
            return "Resource not found"
        case .fileTooLarge:
            return "File is too large to upload"
        case .serverError(let code, let detail):
            // Prefer the engine's message; keep the code visible for support.
            if let detail { return "\(detail) (HTTP \(code))" }
            return "Server error (HTTP \(code))"
        }
    }
}
