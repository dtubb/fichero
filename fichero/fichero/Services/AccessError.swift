import Foundation

/// Typed taxonomy of the ways an authenticated engine request can fail (F5).
///
/// The top invariant of the connection/auth work is *never a silent 403, blank
/// pane, or forever-spinner* — every failure must surface **why** and **what to
/// do next**. A bare `Error`/`Int` status can't carry that, so each request
/// failure is classified into one of these cases; the `recovery` hint then tells
/// the UI which action to offer (sign in / request access / reset pin / restart).
enum AccessError: LocalizedError, Equatable {
    /// 401 — the engine did not accept our credentials. Next: sign in.
    case unauthenticated
    /// 403 — authenticated but not permitted for this resource. `reason` is the
    /// engine's machine code (when the structured denial body carries one);
    /// `message` is its human sentence. Next: request access.
    case forbidden(reason: String?, message: String?)
    /// TLS / certificate-pin rejection (`errSSLXCertChainInvalid` -9807 & the
    /// rest of the SSL OSStatus range). Next: reset the pinned certificate.
    case tlsPinFailure
    /// The transport could not reach the engine at all (down / wrong host /
    /// timed out). Next: restart the engine or retry.
    case engineUnreachable
    /// Any other failure, carrying the underlying description so it is never
    /// swallowed silently.
    case transport(String)

    /// The single next-step the UI should offer for this failure.
    enum Recovery: Equatable {
        case signIn
        case requestAccess
        case resetPin
        case restartEngine
        case retry
    }

    var recovery: Recovery {
        switch self {
        case .unauthenticated: return .signIn
        case .forbidden: return .requestAccess
        case .tlsPinFailure: return .resetPin
        case .engineUnreachable: return .restartEngine
        case .transport: return .retry
        }
    }

    var errorDescription: String? {
        switch self {
        case .unauthenticated:
            return "You're not signed in to this engine."
        case .forbidden(_, let message):
            return message ?? "You don't have access to this."
        case .tlsPinFailure:
            return "The engine's security certificate didn't match the pinned one."
        case .engineUnreachable:
            return "The Fichero engine isn't reachable."
        case .transport(let description):
            return description
        }
    }

    // MARK: - Classification

    /// Map an HTTP status (+ optional raw body) to a case, or `nil` if the status
    /// isn't an access failure (2xx, 404, 5xx handled by callers). Only 401/403
    /// are access-denial statuses.
    static func classify(statusCode: Int, body: Data?) -> AccessError? {
        switch statusCode {
        case 401:
            return .unauthenticated
        case 403:
            let denial = body.flatMap(DenialBody.decode)
            return .forbidden(reason: denial?.reason, message: denial?.message)
        default:
            return nil
        }
    }

    /// Map a thrown transport error to a case. TLS/pin failures are detected by
    /// walking the underlying-error chain for the SSL OSStatus range (the -9807
    /// pin rejection is nested under `NSUnderlyingErrorKey`, not on the top-level
    /// `URLError`), then the `URLError.Code` decides unreachable vs. other TLS.
    static func classify(_ error: Error) -> AccessError {
        if containsTLSFailure(error as NSError) {
            return .tlsPinFailure
        }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .cannotConnectToHost, .cannotFindHost, .timedOut,
                 .networkConnectionLost, .notConnectedToInternet, .dnsLookupFailed:
                return .engineUnreachable
            case .secureConnectionFailed, .serverCertificateUntrusted,
                 .serverCertificateHasBadDate, .serverCertificateHasUnknownRoot,
                 .serverCertificateNotYetValid, .clientCertificateRejected,
                 .clientCertificateRequired:
                return .tlsPinFailure
            default:
                break
            }
        }
        return .transport(error.localizedDescription)
    }

    /// True if any error in the underlying chain is an SSL OSStatus failure.
    /// -9800…-9849 is the `errSSL*` range (-9807 = `errSSLXCertChainInvalid`, the
    /// pin-mismatch code). ponytail: depth-capped at 8 to avoid a cyclic chain.
    private static func containsTLSFailure(_ error: NSError) -> Bool {
        var current: NSError? = error
        var depth = 0
        while let err = current, depth < 8 {
            if (-9849...(-9800)).contains(err.code) { return true }
            current = err.userInfo[NSUnderlyingErrorKey] as? NSError
            depth += 1
        }
        return false
    }
}

extension AccessError {
    /// Best-effort lift of an arbitrary thrown/stored error into the access
    /// taxonomy, or `nil` when it isn't an access failure (so the caller keeps
    /// its generic error UI — no regression, just no richer denial view).
    ///
    /// Recognizes an already-typed `AccessError` and the `DocumentStore`'s
    /// collapsed `.unauthorized` bucket (its 401/403 path). The collapsed case
    /// maps to `.forbidden` with no message; the access-denied view then uses
    /// identity to decide sign-in vs. request-access.
    static func from(_ error: Error?) -> AccessError? {
        guard let error else { return nil }
        if let access = error as? AccessError { return access }
        if let storeError = error as? DocumentStoreError, case .unauthorized = storeError {
            return .forbidden(reason: nil, message: nil)
        }
        return nil
    }
}

/// Permissive decoder for the engine's structured denial body. FastAPI raises
/// `HTTPException(403, detail=…)` where `detail` is either a plain string or a
/// nested object — so we accept `{"detail": "msg"}`, `{"detail": {"reason", …}}`,
/// and a bare top-level `{"reason", "message"}`. Returns `nil` when nothing
/// usable is present (the caller then falls back to a generic message).
struct DenialBody: Equatable {
    let reason: String?
    let message: String?

    static func decode(_ data: Data) -> DenialBody? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if let detail = object["detail"] as? String {
            return DenialBody(reason: nil, message: detail)
        }
        let scope = (object["detail"] as? [String: Any]) ?? object
        let reason = scope["reason"] as? String
        let message = (scope["message"] as? String) ?? (scope["detail"] as? String)
        guard reason != nil || message != nil else { return nil }
        return DenialBody(reason: reason, message: message)
    }
}
