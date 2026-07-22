import Foundation
import OpenAPIRuntime

public extension Error {
    /// Returns `true` when this error (or an error it wraps) represents a
    /// cancelled/superseded async operation rather than a genuine failure.
    ///
    /// Cancellation is normal control flow: a view was torn down, a newer
    /// selection superseded an in-flight request, a task was cancelled. It must
    /// never be logged as an error or surfaced to the user as a failure state.
    var isCancellationError: Bool {
        if self is CancellationError { return true }
        if let clientError = self as? ClientError { return clientError.underlyingError.isCancellationError }
        if let urlError = self as? URLError, urlError.code == .cancelled { return true }
        return false
    }
}
