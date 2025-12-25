import Foundation

/// Represents different types of errors that can occur in the application
enum ErrorType: String, Codable {
    case network
    case validation
    case permission
    case notFound
    case conflict
    case timeout
    case unknown
    case database
    case fileSystem
    case parsing
    case authentication
    case authorization
    case serviceUnavailable
    case rateLimit
    case invalidInput
    case operationCancelled
}

/// Represents the severity level of an error
enum ErrorSeverity: String, Codable {
    case critical
    case high
    case medium
    case low
    case info
}

/// Model representing an error in the application
struct ErrorModel: Identifiable, Codable, Error {
    let id: UUID
    let type: ErrorType
    let severity: ErrorSeverity
    let title: String
    let message: String
    let timestamp: Date
    let context: [String: String]?
    let isRecoverable: Bool
    let recoverySuggestion: String?
    let helpLink: URL?
    
    init(
        id: UUID = UUID(),
        type: ErrorType,
        severity: ErrorSeverity,
        title: String,
        message: String,
        timestamp: Date = Date(),
        context: [String: String]? = nil,
        isRecoverable: Bool = false,
        recoverySuggestion: String? = nil,
        helpLink: URL? = nil
    ) {
        self.id = id
        self.type = type
        self.severity = severity
        self.title = title
        self.message = message
        self.timestamp = timestamp
        self.context = context
        self.isRecoverable = isRecoverable
        self.recoverySuggestion = recoverySuggestion
        self.helpLink = helpLink
    }
}

// MARK: - Convenience Initializers

extension ErrorModel {
    /// Create a network error
    static func networkError(
        message: String,
        context: [String: String]? = nil,
        isRecoverable: Bool = true
    ) -> ErrorModel {
        ErrorModel(
            type: .network,
            severity: .medium,
            title: "Network Error",
            message: message,
            context: context,
            isRecoverable: isRecoverable,
            recoverySuggestion: "Please check your internet connection and try again."
        )
    }

    /// Create a validation error
    static func validationError(
        message: String,
        context: [String: String]? = nil
    ) -> ErrorModel {
        ErrorModel(
            type: .validation,
            severity: .low,
            title: "Validation Error",
            message: message,
            context: context,
            isRecoverable: true,
            recoverySuggestion: "Please correct the input and try again."
        )
    }

    /// Create a permission error
    static func permissionError(
        message: String,
        context: [String: String]? = nil
    ) -> ErrorModel {
        ErrorModel(
            type: .permission,
            severity: .high,
            title: "Permission Denied",
            message: message,
            context: context,
            isRecoverable: false,
            recoverySuggestion: "Please check your permissions and try again."
        )
    }

    /// Create a file system error
    static func fileSystemError(
        message: String,
        context: [String: String]? = nil,
        isRecoverable: Bool = true
    ) -> ErrorModel {
        ErrorModel(
            type: .fileSystem,
            severity: .medium,
            title: "File System Error",
            message: message,
            context: context,
            isRecoverable: isRecoverable,
            recoverySuggestion: "Please check the file and try again."
        )
    }

    /// Create a database error
    static func databaseError(
        message: String,
        context: [String: String]? = nil,
        isRecoverable: Bool = false
    ) -> ErrorModel {
        ErrorModel(
            type: .database,
            severity: .high,
            title: "Database Error",
            message: message,
            context: context,
            isRecoverable: isRecoverable,
            recoverySuggestion: "Please restart the application."
        )
    }
}