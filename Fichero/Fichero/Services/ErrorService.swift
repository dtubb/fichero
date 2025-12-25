import Foundation
import os.log

/// Service for centralized error handling and management
class ErrorService: ObservableObject {
    
    // Singleton instance
    static let shared = ErrorService()
    
    // Error history for debugging and analytics
    @Published private(set) var errorHistory: [ErrorModel] = []
    
    // Maximum number of errors to keep in history
    private let maxErrorHistoryCount = 100
    
    // Logger for error service
    private let logger = Logger(subsystem: "com.fichero.sidebar", category: "ErrorService")
    
    // Private initializer for singleton pattern
    private init() {}
    
    /// Report an error and handle it appropriately
    /// - Parameters:
    ///   - error: The error to report
    ///   - showUserFeedback: Whether to show feedback to the user
    ///   - completion: Completion handler with error handling result
    func reportError(
        _ error: Error,
        showUserFeedback: Bool = true,
        completion: ((ErrorModel) -> Void)? = nil
    ) {
        let errorModel = createErrorModel(from: error)
        
        // Log the error
        logError(errorModel)
        
        // Add to error history
        addToErrorHistory(errorModel)
        
        // Show user feedback if requested
        if showUserFeedback {
            showUserFeedback(for: errorModel)
        }
        
        // Call completion handler
        completion?(errorModel)
    }
    
    /// Report an error with custom error model
    /// - Parameters:
    ///   - errorModel: The error model to report
    ///   - showUserFeedback: Whether to show feedback to the user
    func reportError(
        _ errorModel: ErrorModel,
        showUserFeedback: Bool = true
    ) {
        // Log the error
        logError(errorModel)
        
        // Add to error history
        addToErrorHistory(errorModel)
        
        // Show user feedback if requested
        if showUserFeedback {
            showUserFeedback(for: errorModel)
        }
    }
    
    /// Create an ErrorModel from a standard Error
    /// - Parameter error: The error to convert
    /// - Returns: ErrorModel representation
    private func createErrorModel(from error: Error) -> ErrorModel {
        // Check if it's already an ErrorModel
        if let errorModel = error as? ErrorModel {
            return errorModel
        }
        
        // Handle NSError specifically
        if let nsError = error as NSError? {
            return createErrorModel(from: nsError)
        }
        
        // Default error model for unknown errors
        return ErrorModel(
            type: .unknown,
            severity: .medium,
            title: "Error",
            message: error.localizedDescription,
            context: ["error_type": String(describing: type(of: error))]
        )
    }
    
    /// Create an ErrorModel from NSError
    /// - Parameter nsError: The NSError to convert
    /// - Returns: ErrorModel representation
    private func createErrorModel(from nsError: NSError) -> ErrorModel {
        let errorType: ErrorType
        let severity: ErrorSeverity
        
        // Map NSError domain and code to our error types
        switch nsError.domain {
        case "NSCocoaErrorDomain":
            switch nsError.code {
            case NSFileReadNoSuchFileError, NSFileReadNoPermissionError:
                errorType = .fileSystem
                severity = .medium
            case NSFileWriteNoPermissionError, NSFileWriteVolumeReadOnlyError:
                errorType = .permission
                severity = .high
            case NSKeyValueValidationError:
                errorType = .validation
                severity = .low
            default:
                errorType = .unknown
                severity = .medium
            }
        case "NSURLErrorDomain":
            errorType = .network
            severity = nsError.code == NSURLErrorNotConnectedToInternet ? .high : .medium
        case "com.fichero.sidebar":
            errorType = .validation
            severity = .low
        default:
            errorType = .unknown
            severity = .medium
        }
        
        return ErrorModel(
            type: errorType,
            severity: severity,
            title: "Error",
            message: nsError.localizedDescription,
            context: [
                "domain": nsError.domain,
                "code": "\(nsError.code)",
                "userInfo": nsError.userInfo.description
            ]
        )
    }
    
    /// Log an error using the system logger
    /// - Parameter errorModel: The error to log
    private func logError(_ errorModel: ErrorModel) {
        let logMessage = "[ERROR] [\(errorModel.type.rawValue.uppercased())] [\(errorModel.severity.rawValue.uppercased())] \(errorModel.title): \(errorModel.message)"
        
        switch errorModel.severity {
        case .critical, .high:
            logger.error("\(logMessage, privacy: .public)")
        case .medium:
            logger.warning("\(logMessage, privacy: .public)")
        case .low, .info:
            logger.info("\(logMessage, privacy: .public)")
        }
        
        // Log context if available
        if let context = errorModel.context {
            for (key, value) in context {
                logger.debug("  \(key, privacy: .public): \(value, privacy: .public)")
            }
        }
    }
    
    /// Add an error to the error history
    /// - Parameter errorModel: The error to add
    private func addToErrorHistory(_ errorModel: ErrorModel) {
        DispatchQueue.main.async {
            self.errorHistory.insert(errorModel, at: 0)
            
            // Trim history if it exceeds maximum count
            if self.errorHistory.count > self.maxErrorHistoryCount {
                self.errorHistory.removeLast()
            }
        }
    }
    
    /// Show user feedback for an error
    /// - Parameter errorModel: The error to show feedback for
    private func showUserFeedback(for errorModel: ErrorModel) {
        // For now, just log that we would show user feedback
        // In a real implementation, this would show alerts, toasts, etc.
        logger.info("Showing user feedback for error: \(errorModel.title, privacy: .public)")
        
        // Show alert based on severity
        switch errorModel.severity {
        case .critical, .high:
            showCriticalErrorAlert(errorModel)
        case .medium:
            showMediumErrorAlert(errorModel)
        case .low, .info:
            showLowErrorAlert(errorModel)
        }
    }
    
    /// Show alert for critical/high severity errors
    /// - Parameter errorModel: The error to show
    private func showCriticalErrorAlert(_ errorModel: ErrorModel) {
        DispatchQueue.main.async {
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = errorModel.title
                alert.informativeText = errorModel.message
                
                if let suggestion = errorModel.recoverySuggestion {
                    alert.informativeText += "\n\n\(suggestion)"
                }
                
                alert.addButton(withTitle: "OK")
                
                if errorModel.isRecoverable {
                    alert.addButton(withTitle: "Retry")
                }
                
                let response = alert.runModal()
                
                if response == .alertSecondButtonReturn && errorModel.isRecoverable {
                    // User wants to retry - this would be handled by the calling code
                    self.logger.info("User requested retry for error: \(errorModel.id.uuidString, privacy: .public)")
                }
            }
        }
    }
    
    /// Show alert for medium severity errors
    /// - Parameter errorModel: The error to show
    private func showMediumErrorAlert(_ errorModel: ErrorModel) {
        DispatchQueue.main.async {
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = errorModel.title
                alert.informativeText = errorModel.message
                
                if let suggestion = errorModel.recoverySuggestion {
                    alert.informativeText += "\n\n\(suggestion)"
                }
                
                alert.addButton(withTitle: "OK")
                
                if errorModel.isRecoverable {
                    alert.addButton(withTitle: "Retry")
                }
                
                alert.runModal()
            }
        }
    }
    
    /// Show alert for low severity errors (toast-style)
    /// - Parameter errorModel: The error to show
    private func showLowErrorAlert(_ errorModel: ErrorModel) {
        DispatchQueue.main.async {
            if let window = NSApp.keyWindow {
                let alert = NSAlert()
                alert.messageText = errorModel.title
                alert.informativeText = errorModel.message
                alert.addButton(withTitle: "OK")
                alert.runModal()
            }
        }
    }
    
    /// Get recent errors for debugging purposes
    /// - Parameter limit: Maximum number of errors to return
    /// - Returns: Array of recent errors
    func getRecentErrors(limit: Int = 10) -> [ErrorModel] {
        return Array(errorHistory.prefix(limit))
    }
    
    /// Clear error history
    func clearErrorHistory() {
        DispatchQueue.main.async {
            self.errorHistory.removeAll()
        }
    }
    
    /// Handle error recovery attempt
    /// - Parameters:
    ///   - errorModel: The error to recover from
    ///   - recoveryAction: The recovery action to attempt
    ///   - completion: Completion handler with recovery result
    func attemptRecovery(
        for errorModel: ErrorModel,
        recoveryAction: @escaping () async throws -> Void,
        completion: @escaping (Result<Void, Error>) -> Void
    ) {
        Task {
            do {
                try await recoveryAction()
                logger.info("Successfully recovered from error: \(errorModel.id.uuidString, privacy: .public)")
                completion(.success(()))
            } catch {
                let recoveryError = createErrorModel(from: error)
                reportError(recoveryError)
                logger.error("Recovery failed for error: \(errorModel.id.uuidString, privacy: .public)")
                completion(.failure(recoveryError))
            }
        }
    }
}