import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SandboxAccessService")

/// Hands the RUNNING sandboxed engine a security-scoped bookmark for a library the
/// user just picked (#3773), through `POST /api/sandbox/security-scoped-access`.
///
/// Why this exists: the spawn-time handoff is an environment variable, and an
/// environment cannot change after the process starts. The user picks libraries
/// while the engine is already running — including the very first library a new
/// user ever picks — and the engine is never restarted. Without this call those
/// libraries stay unreadable until the app relaunches.
///
/// Used by every SANDBOXED app (all configs since 2026-07-29) — the caller gates
/// on the runtime `SandboxEnvironment.isSandboxed`, never a build flag (the old
/// MAS-flag gate compiled this handoff to a no-op in non-MAS builds; fixed
/// 2026-08-08). An unsandboxed engine can already open the library directly.
///
/// A thin service over the generated OpenAPI client — no hand-rolled URLSession.
@MainActor
class SandboxAccessService {
    let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Grant the engine access to `path` using `bookmark` (app-scoped, security-scoped).
    ///
    /// Idempotent on the engine side: re-sending a path it already holds reports
    /// success without resolving the bookmark again, so a retry is free and a
    /// double-send is harmless.
    ///
    /// Throws rather than returning false on refusal. "Granted" has to mean granted:
    /// the app is about to open this library, and a grant that quietly did nothing
    /// would surface later as an inscrutable DuckDB permission error instead of a
    /// clear "Fichero can't open this folder".
    func grantAccess(toPath path: String, bookmark: Data) async throws {
        let response = try await client.api.createSecurityScopedAccessApiSandboxSecurityScopedAccessPost(
            .init(body: .json(.init(path: path, bookmark: bookmark.base64EncodedString())))
        )

        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            guard body.granted else {
                // The engine reports 200 only when the grant holds, so this is a
                // contract violation rather than an expected refusal (that is a 400).
                throw SandboxAccessServiceError.notGranted(path: path, reason: "engine returned granted=false")
            }
            if body.alreadyHeld == true {
                logger.debug("Engine already had security-scoped access: \(path, privacy: .public)")
            } else {
                logger.info("Engine granted security-scoped access: \(path, privacy: .public)")
            }
        case .badRequest:
            // The bookmark could not be turned into access — stale, malformed, or
            // startAccessingSecurityScopedResource() refused it.
            throw SandboxAccessServiceError.notGranted(
                path: path,
                reason: "the engine could not open this folder with the permission it was given"
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SandboxAccessServiceError.notGranted(
                path: path,
                reason: detail?.detail?.description ?? "validation error"
            )
        case .undocumented(let statusCode, let payload):
            // Drain the engine's own sentence (#4562's sibling): a bare
            // "unexpected response (403)" survived TWO diagnosis rounds on
            // 2026-08-08 because the body naming the actual refuser was
            // discarded right here.
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                throw SandboxAccessServiceError.notGranted(
                    path: path,
                    reason: "the engine refused (\(statusCode)): \(denial.localizedDescription)"
                )
            }
            throw SandboxAccessServiceError.unexpectedResponse(statusCode)
        }
    }
}

enum SandboxAccessServiceError: LocalizedError {
    case notGranted(path: String, reason: String)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .notGranted(let path, let reason):
            return "Fichero can't open “\(path)”: \(reason)"
        case .unexpectedResponse(let statusCode):
            return "The engine returned an unexpected response (\(statusCode)) when granting folder access."
        }
    }
}
