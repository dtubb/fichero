import Foundation
import OpenAPIRuntime

public extension Error {
    /// True when this error is a task cancellation — including when the generated
    /// client wraps it. swift-openapi's `ClientError` carries the transport's
    /// `CancellationError` as `underlyingError`, so a bare `catch is
    /// CancellationError` misses a superseded request and mislogs it as a failure.
    /// Unwrap the chain so callers can treat cancellation as "superseded, keep
    /// state" instead of an error.
    var isCancellationError: Bool {
        if self is CancellationError { return true }
        if let clientError = self as? ClientError {
            return clientError.underlyingError.isCancellationError
        }
        if let urlError = self as? URLError, urlError.code == .cancelled { return true }
        return false
    }
}
