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
    /// 401/403 whose structured body carries `code == "stale_bootstrap_token"`:
    /// the app holds a loopback bootstrap token the engine has since rotated
    /// away from — the sandbox-relaunch case (#3052 / auth.py `_is_stale_sandbox_
    /// bootstrap_token`). Distinct from `.unauthenticated` because *signing in
    /// cannot fix it* — the engine must re-mint/re-sync the token. Next: restart.
    case staleBootstrapToken
    /// 403 — authenticated but not permitted for this resource. `reason` is the
    /// engine's machine code (when the structured denial body carries one);
    /// `message` is its human sentence. Next: request access.
    case forbidden(reason: String?, message: String?)
    /// A paired device's token has expired or been revoked host-side (#3096):
    /// the engine returns 401 `{"detail": "device token expired"}` (auth.py). A
    /// device has no username/password sign-in — the only recovery is to re-pair
    /// (scan a fresh QR on the Mac). Next: re-pair.
    case deviceAccessExpired
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
        case rePair
        case retry
    }

    var recovery: Recovery {
        switch self {
        case .unauthenticated: return .signIn
        case .staleBootstrapToken: return .restartEngine
        case .deviceAccessExpired: return .rePair
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
        case .staleBootstrapToken:
            return "This app's saved engine token is out of date. Restart the engine to refresh it."
        case .deviceAccessExpired:
            return "This device's access has expired. Re-pair with the Mac to continue."
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
        let denial = body.flatMap(DenialBody.decode)
        // Discriminators are status-agnostic (key on the body, not the status):
        // the engine returns these as 401 today (auth.py), but matching the marker
        // keeps classification correct if a path 403s them instead.
        if denial?.code == "stale_bootstrap_token" {
            return .staleBootstrapToken
        }
        if isDeviceExpiredMarker(denial) {
            return .deviceAccessExpired
        }
        switch statusCode {
        case 401:
            return .unauthenticated
        case 403:
            return .forbidden(reason: denial?.reason, message: denial?.message)
        default:
            return nil
        }
    }

    /// The engine signals an expired/revoked device token as a 401 whose `detail`
    /// is exactly `"device token expired"` (auth.py `_authenticate_device_token`).
    /// It carries no structured `code` yet, so we also accept a future
    /// `code == "device_token_expired"` to stay robust if the backend adds one.
    private static func isDeviceExpiredMarker(_ denial: DenialBody?) -> Bool {
        denial?.code == "device_token_expired" || denial?.message == "device token expired"
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

// MARK: - Denials that arrive as a line stream

extension AccessError {
    /// Read a denial body that came back as a LINE STREAM and return the
    /// engine's own sentence (#4532).
    ///
    /// `FicheroClient.streamLines` hands the body back as `lines` whatever the
    /// status, so an SSE consumer that sees a 403 already HAS the server's
    /// explanation — the two stream services simply dropped it on the floor and
    /// logged a hardcoded guess ("no role on library") instead. That guess sent
    /// half an hour of diagnosis down the multi-user path for a denial that was
    /// actually "Library path is not in an allowed location".
    ///
    /// Returns `nil` when the body carries nothing usable, so the caller can say
    /// "the engine refused and gave no reason" — which is still the truth, and
    /// still better than inventing one.
    ///
    /// ponytail: drains at most `maxLines`. A denial body is a single short JSON
    /// object; the cap is there so a mis-wired call on a 200 (an endless SSE
    /// stream) can't hang the loop forever.
    static func denialMessage(
        fromBodyLines lines: AsyncThrowingStream<String, any Error>,
        maxLines: Int = 8
    ) async -> String? {
        var collected: [String] = []
        var seen = 0
        do {
            for try await line in lines {
                collected.append(line)
                seen += 1
                if seen >= maxLines { break }
            }
        } catch {
            // A truncated denial body is still worth whatever arrived before the
            // error; falling through keeps that rather than discarding it.
        }

        let joined = collected.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !joined.isEmpty else { return nil }

        if let denial = DenialBody.decode(Data(joined.utf8)) {
            return denial.message ?? denial.reason ?? denial.code
        }
        // Not JSON — return the raw text rather than nothing. The engine said
        // something; the user is better served by it than by silence.
        return joined
    }
}

/// Permissive decoder for the engine's structured denial body. The engine emits
/// a top-level machine `code` (e.g. `"stale_bootstrap_token"`, auth.py) alongside
/// a `detail` that is either a plain string or a nested object — so we accept
/// `{"detail": "msg", "code": "x"}`, `{"detail": {"reason", "message"}}`, and a
/// bare top-level `{"reason", "message"}`. Returns `nil` when nothing usable is
/// present (the caller then falls back to a generic message).
struct DenialBody: Equatable {
    /// Top-level machine code, the primary discriminator (e.g. stale token).
    let code: String?
    let reason: String?
    let message: String?

    static func decode(_ data: Data) -> DenialBody? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        // Capture `code` first — the string-`detail` early-return used to drop it.
        let code = object["code"] as? String
        let detailString = object["detail"] as? String
        let scope = (object["detail"] as? [String: Any]) ?? object
        // reason prefers an explicit field, else the top-level code (so a 403's
        // machine reason still reaches `.forbidden(reason:)`).
        let reason = (scope["reason"] as? String) ?? code
        let message = detailString ?? (scope["message"] as? String) ?? (scope["detail"] as? String)
        guard code != nil || reason != nil || message != nil else { return nil }
        return DenialBody(code: code, reason: reason, message: message)
    }
}
