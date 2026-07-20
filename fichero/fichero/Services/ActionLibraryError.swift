import Foundation

// MARK: - Errors

enum ActionLibraryError: LocalizedError {
    case invalidURL
    case serverError
    case cannotDeleteBuiltin

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .serverError:
            return "Server error"
        case .cannotDeleteBuiltin:
            return "Cannot delete built-in action"
        }
    }
}
