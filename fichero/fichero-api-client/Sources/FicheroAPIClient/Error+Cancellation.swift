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

public extension Error {
    /// True when this error is (or wraps) an HTTP 404 from the generated
    /// client — the "this document no longer exists" signal callers use for
    /// stale-selection recovery (2026-08-09): a restored selection can point
    /// at a document of a deleted/recreated library, and a 404 there means
    /// "fall back to the root set", never "the engine is down".
    var isNotFoundError: Bool {
        if let clientError = self as? ClientError {
            if let response = clientError.response, response.status.code == 404 {
                return true
            }
            return clientError.underlyingError.isNotFoundError
        }
        return false
    }
}

public extension Error {
    /// What went wrong in words that name the part: a decode error says which field and where ("the answer has no
    /// \"problems\" (at recipe › steps › 0)"), never Foundation's "The data couldn't be read because it is missing".
    /// Any other error keeps its own description. Unwraps the generated client's `ClientError`.
    var inWords: String {
        if let clientError = self as? ClientError { return clientError.underlyingError.inWords }
        guard let decoding = self as? DecodingError else { return localizedDescription }
        func path(_ context: DecodingError.Context) -> String {
            let parts = context.codingPath.map { $0.intValue.map(String.init) ?? $0.stringValue }
            return parts.isEmpty ? "" : " (at \(parts.joined(separator: " › ")))"
        }
        switch decoding {
        case .keyNotFound(let key, let context):
            return "the answer has no \"\(key.stringValue)\"\(path(context))"
        case .valueNotFound(_, let context):
            return "the answer has an empty value\(path(context))"
        case .typeMismatch(_, let context), .dataCorrupted(let context):
            return "the answer holds something unexpected\(path(context)): \(context.debugDescription)"
        @unknown default:
            return localizedDescription
        }
    }
}
