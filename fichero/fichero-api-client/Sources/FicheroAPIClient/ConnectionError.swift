import Foundation
import HTTPTypes
import OpenAPIRuntime
import os

/// A self-describing transport failure for the Fichero engine client.
///
/// The generated OpenAPI client surfaces a dial failure as either a bare
/// `URLError` (e.g. `NSURLErrorDomain -1004` "could not connect to the server")
/// or an opaque `OpenAPIRuntime.ClientError` whose `description` buries the real
/// cause under request/response dumps. Neither names *what actually went wrong*
/// or *which transport it went wrong on*. `ConnectionError` classifies such a
/// failure into a small, named ``Kind`` and prints a one-line human summary —
/// Daniel's observability mandate ("classify it and report the actual cause").
///
/// This type is **additive and observability-focused**: it is meant for
/// classification-and-logging at the transport seam, NOT to replace the ~20
/// per-service `LocalizedError` enums callers `catch` on. Producing it via
/// ``classify(_:transport:operationID:)`` never changes control flow — the
/// caller decides whether to log it, wrap it, or ignore it.
public struct ConnectionError: Error, CustomStringConvertible {

    /// The classified cause of the failure.
    public enum Kind: String, Sendable, Equatable {
        /// The engine wasn't reachable — the `-1004` / `ECONNREFUSED (61)` family
        /// (`URLError.cannotConnectToHost` / `.networkConnectionLost` /
        /// `.cannotFindHost`). The commonest symptom of a not-yet-started engine
        /// or a wrong-transport dial.
        case connectionRefused
        /// The operation was cancelled (task cancellation or `URLError.cancelled`).
        /// Usually benign — a superseded request, not a fault.
        case cancelled
        /// The request timed out (`URLError.timedOut`).
        case timedOut
        /// TLS/certificate negotiation failed (`URLError.secureConnectionFailed`
        /// or a `serverCertificate*` trust failure) — e.g. a pinning mismatch.
        case tlsFailure
        /// The endpoint returned/represented a 404-style "not found".
        case notFound
        /// The request was rejected for auth reasons (401/403-style).
        case unauthorized
        /// The transport itself couldn't be established or used (e.g. an
        /// unassemblable request target, or the in-process engine failing to boot).
        case transportUnavailable
        /// The endpoint returned a retryable 5xx server failure.
        case serverError
        /// The response or request shape was malformed (bad 4xx request,
        /// malformed response body, or `DecodingError`).
        case malformedResponse
        /// Response decoding failed (`DecodingError`). Kept for source
        /// compatibility; new classification uses ``malformedResponse``.
        case decoding
        /// Anything not matched above; inspect ``underlying``.
        case other
    }

    /// Coarse failure policy for retry loops and UI messaging.
    public enum FailureClass: String, Sendable, Equatable {
        /// The operation may succeed on a later attempt (network, timeout,
        /// transport unavailable, or HTTP 5xx).
        case retryable
        /// The operation was cancelled by caller/task teardown; not a fault and
        /// not a retry signal.
        case cancelled
        /// Retrying the same request without a state/configuration change should
        /// not help (auth, 404, TLS/pinning, malformed payloads, unknown errors).
        case fatal
    }

    /// Synthetic underlying error for classified HTTP status failures.
    public struct HTTPStatusFailure: Error, CustomStringConvertible, Sendable, Equatable {
        public let statusCode: Int
        public let endpointPath: String?

        public var description: String {
            if let endpointPath {
                return "HTTP \(statusCode) from \(endpointPath)"
            }
            return "HTTP \(statusCode)"
        }
    }

    /// Which transport the failed call dialed with.
    public let transport: TransportMode
    /// The OpenAPI operation identifier, when known (e.g. `inspector_…`).
    public let operationID: String?
    /// The request path, when known (e.g. `/api/documents/…/inspector`).
    public let endpointPath: String?
    /// The classified cause.
    public let kind: Kind
    /// The original error, preserved verbatim for deep debugging.
    public let underlying: any Error

    /// Whether callers should retry this failure, treat it as benign
    /// cancellation, or surface it as fatal.
    public var failureClass: FailureClass {
        switch kind {
        case .connectionRefused, .timedOut, .transportUnavailable, .serverError:
            return .retryable
        case .cancelled:
            return .cancelled
        case .tlsFailure, .notFound, .unauthorized, .malformedResponse, .decoding, .other:
            return .fatal
        }
    }

    /// Convenience boolean for retry loops at the API-client boundary.
    public var isRetryable: Bool { failureClass == .retryable }

    /// Creates a classified connection error. Prefer
    /// ``classify(_:transport:operationID:)`` over calling this directly.
    public init(
        transport: TransportMode,
        operationID: String?,
        endpointPath: String?,
        kind: Kind,
        underlying: any Error
    ) {
        self.transport = transport
        self.operationID = operationID
        self.endpointPath = endpointPath
        self.kind = kind
        self.underlying = underlying
    }

    /// Classify an arbitrary error thrown by the generated client (or the
    /// streaming/request seams) into a named ``ConnectionError``.
    ///
    /// Unwraps, in order:
    /// - an existing ``ConnectionError`` (returned unchanged),
    /// - `OpenAPIRuntime.ClientError` — lifting its `operationID` and request
    ///   `path`, then classifying its `underlyingError`,
    /// - `URLError` — mapping the transport code to a ``Kind``,
    /// - `CancellationError` / any cancellation-shaped error → ``Kind/cancelled``,
    /// - `DecodingError` → ``Kind/malformedResponse``,
    /// - `FicheroStreamingError` → ``Kind/transportUnavailable``.
    ///
    /// - Parameters:
    ///   - error: The thrown error to classify.
    ///   - transport: The transport the failing call used.
    ///   - operationID: A fallback operation id when the error doesn't carry one.
    public static func classify(
        _ error: any Error,
        transport: TransportMode,
        operationID: String? = nil
    ) -> ConnectionError {
        // Already classified — don't re-wrap.
        if let already = error as? ConnectionError {
            return already
        }

        // OpenAPIRuntime.ClientError carries the richest context: the operation
        // id, the request (hence path), and the true `underlyingError`. Lift that
        // context and classify the cause underneath.
        if let clientError = error as? ClientError {
            let path = clientError.request?.path ?? clientError.baseURL?.absoluteString
            return ConnectionError(
                transport: transport,
                operationID: operationID ?? clientError.operationID,
                endpointPath: path,
                kind: classifyKind(clientError.underlyingError),
                underlying: clientError.underlyingError
            )
        }

        return ConnectionError(
            transport: transport,
            operationID: operationID,
            endpointPath: nil,
            kind: classifyKind(error),
            underlying: error
        )
    }

    /// Classify an HTTP response status at the API-client boundary.
    ///
    /// HTTP 5xx is retryable server-side/transient failure. Auth failures, 404,
    /// and malformed 4xx requests are fatal for the same request.
    public static func classifyHTTPStatus(_ statusCode: Int) -> Kind? {
        switch statusCode {
        case 500...599:
            return .serverError
        case 401, 403:
            return .unauthorized
        case 404:
            return .notFound
        case 400...499:
            return .malformedResponse
        default:
            return nil
        }
    }

    /// Build a classified HTTP status failure while preserving the status as the
    /// underlying error for diagnostics.
    public static func httpStatus(
        _ statusCode: Int,
        transport: TransportMode,
        operationID: String? = nil,
        endpointPath: String? = nil
    ) -> ConnectionError? {
        guard let kind = classifyHTTPStatus(statusCode) else { return nil }
        return ConnectionError(
            transport: transport,
            operationID: operationID,
            endpointPath: endpointPath,
            kind: kind,
            underlying: HTTPStatusFailure(statusCode: statusCode, endpointPath: endpointPath)
        )
    }

    /// Map a leaf error to a ``Kind``. Unwraps a nested `ClientError` first, so
    /// callers that hand us either layer get the same answer.
    private static func classifyKind(_ error: any Error) -> Kind {
        if let clientError = error as? ClientError {
            return classifyKind(clientError.underlyingError)
        }

        // Cancellation can arrive as a Swift `CancellationError`, a
        // `URLError(.cancelled)`, or a `ClientError`-wrapped cancellation — the
        // shared `Error.isCancellationError` helper (Error+Cancellation.swift)
        // unwraps all three.
        if error.isCancellationError {
            return .cancelled
        }

        if error is FicheroStreamingError {
            return .transportUnavailable
        }

        if error is DecodingError {
            return .malformedResponse
        }

        if let urlError = error as? URLError {
            switch urlError.code {
            case .cannotConnectToHost, .networkConnectionLost, .cannotFindHost,
                 .notConnectedToInternet, .dnsLookupFailed:
                // The `-1004` / `ECONNREFUSED (61)` family: engine unreachable.
                return .connectionRefused
            case .cancelled:
                return .cancelled
            case .timedOut:
                return .timedOut
            case .secureConnectionFailed,
                 .serverCertificateUntrusted,
                 .serverCertificateHasBadDate,
                 .serverCertificateHasUnknownRoot,
                 .serverCertificateNotYetValid,
                 .clientCertificateRejected,
                 .clientCertificateRequired:
                return .tlsFailure
            case .userAuthenticationRequired:
                return .unauthorized
            case .fileDoesNotExist, .resourceUnavailable:
                return .notFound
            default:
                return .other
            }
        }

        return .other
    }

    // MARK: - CustomStringConvertible

    /// A one-line, human-readable summary naming the transport, the cause, the
    /// operation, and (when known) the path — e.g.
    /// `"UDS transport: connection refused invoking inspector_get (/api/documents/…/inspector) — could not connect to the server"`.
    public var description: String {
        let operation = operationID ?? "<unknown operation>"
        let pathClause = endpointPath.map { " (\($0))" } ?? ""
        let cause = (underlying as NSError).localizedDescription
        return "\(transport.connectionLabel) transport: \(kind.phrase) invoking \(operation)\(pathClause) — \(cause)"
    }
}

public extension FicheroClient {
    /// The shared logger for classified transport failures. `nonisolated` because
    /// it is read from the nonisolated `logConnectionFailure` seam (the transport
    /// dial runs off the main actor); `os.Logger` is `Sendable`, so this is safe.
    nonisolated static let connectionLogger = Logger(subsystem: "app.fichero.fichero", category: "Connection")

    /// Classify a transport failure and log its one-line ``ConnectionError``
    /// summary. This is the observability seam wired into the `streamLines` /
    /// `requestData` transport dials: it names the actual cause (transport +
    /// classified kind + operation + path) instead of leaking a bare
    /// `NSURLErrorDomain -1004`. It NEVER throws or alters control flow — callers
    /// re-throw the original error unchanged.
    ///
    /// Cancellation is logged at `debug` (a superseded request is benign, not a
    /// fault); every other cause is logged at `error`.
    nonisolated static func logConnectionFailure(
        _ error: any Error,
        transport: TransportMode,
        operationID: String?
    ) {
        let classified = ConnectionError.classify(error, transport: transport, operationID: operationID)
        if classified.kind == .cancelled {
            connectionLogger.debug("\(classified.description, privacy: .public)")
        } else {
            connectionLogger.error("\(classified.description, privacy: .public)")
        }
    }
}

private extension ConnectionError.Kind {
    /// The human phrase used in ``ConnectionError/description``.
    var phrase: String {
        switch self {
        case .connectionRefused: return "connection refused"
        case .cancelled: return "cancelled"
        case .timedOut: return "timed out"
        case .tlsFailure: return "TLS failure"
        case .notFound: return "not found"
        case .unauthorized: return "unauthorized"
        case .transportUnavailable: return "transport unavailable"
        case .serverError: return "server error"
        case .malformedResponse: return "malformed response"
        case .decoding: return "decoding failure"
        case .other: return "error"
        }
    }
}

private extension TransportMode {
    /// Short uppercase label for log lines: `HTTPS`, `UDS`, `in-process`.
    var connectionLabel: String {
        switch self {
        case .https: return "HTTPS"
        case .uds: return "UDS"
        #if os(macOS)
        case .inMemory: return "in-process"
        #endif
        }
    }
}
