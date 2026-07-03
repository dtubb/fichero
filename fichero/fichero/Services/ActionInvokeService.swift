import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// The audited-action invocation seam (EPIC #1848).
///
/// Every state-changing UI button should call a *named, typed action* through
/// the ONE backend write choke point — `POST /api/actions/invoke` — instead of
/// hitting a bespoke typed route. That choke point validates params, runs the
/// action, writes an `ActionAudit` row, and broadcasts a change event, so the
/// UI button, the chat agent (#1847), App Intents (#1837), and tests all drive
/// the *same* code path. This is what makes "who changed what" and ⌘Z-undo
/// uniform across every capability.
///
/// `/api/actions/invoke` is not yet in `openapi.json`, so the generated client
/// can't reach it. This extension uses the same hand-written `addEngineAuth`
/// URLRequest seam the other not-yet-generated calls in `EntityServiceGenerated`
/// use (e.g. the library entity-type registry). When the schema is regenerated
/// to include the actions-registry routes, this can collapse onto the generated
/// client like the rest of `/api/actions/*`.
extension ActionLibraryService {
    private var invokeLogger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "ActionInvoke")
    }

    /// Invoke a registered action by name through the audited choke point.
    ///
    /// - Parameters:
    ///   - name: The action name, `"<domain>.<verb>"` (e.g. `"entity.merge"`).
    ///   - params: The action's typed params. Reuse the OpenAPI-generated schema
    ///     where one exists (e.g. `Components.Schemas.EntityMergeRequest`) so the
    ///     wire bytes match the backend Pydantic model exactly (rule #4 — typed
    ///     fields, never `additionalProperties`).
    ///   - originWindow: Optional self-echo de-dup seam for the change stream.
    /// - Returns: The `{ ok, audit_id, changed_domains }` result. `audit_id` is
    ///   captured by the caller for a future per-window ⌘Z (see `LastAction`).
    @discardableResult
    func invokeAction<Params: Encodable>(
        name: String,
        params: Params,
        originWindow: String? = nil
    ) async throws -> ActionInvokeResult {
        let url = client.baseURL.appending(path: "api/actions/invoke")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth(libraryPath: client.currentLibraryPath)
        if let originWindow {
            request.setValue(originWindow, forHTTPHeaderField: "X-Fichero-Origin-Window")
        }

        let encoder = JSONEncoder()
        request.httpBody = try encoder.encode(
            InvokeActionRequest(name: name, params: params, originWindow: originWindow)
        )

        let session = RemoteCertificatePinning.configuredSession()
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            // Surface the FastAPI `detail` string when present, matching the
            // generated services' validation-error mapping.
            let detail = (try? JSONDecoder().decode(ErrorResponse.self, from: data))?.detail
                ?? String(data: data, encoding: .utf8)
                ?? "Action failed"
            invokeLogger.error("invokeAction(\(name)) HTTP \(http.statusCode): \(detail)")
            throw APIError.httpError(statusCode: http.statusCode, message: detail)
        }

        let result = try JSONDecoder().decode(ActionInvokeResult.self, from: data)
        invokeLogger.info("invokeAction(\(name)) ok — audit \(result.auditId)")
        return result
    }

    /// Undo a previously invoked action by replaying its recorded inverse —
    /// `POST /api/actions/audit/{auditId}/undo`. The backend looks up the audit
    /// row, runs the action's `invert`, and writes a *new* audit row for the
    /// undo itself (so the result's `auditId` is the inverse row, not the one
    /// being reversed). This is the ⌘Z seam for #2015: the UI hands back the
    /// `audit_id` it captured at invoke time and the change stream propagates
    /// the reversed state into the open views.
    ///
    /// - Parameters:
    ///   - auditId: The audit row to reverse (captured from `invokeAction`).
    ///   - originWindow: Optional self-echo de-dup seam for the change stream.
    /// - Returns: The `{ ok, audit_id, changed_domains }` result for the undo.
    @discardableResult
    func undoAction(
        auditId: String,
        originWindow: String? = nil
    ) async throws -> ActionInvokeResult {
        let url = client.baseURL.appending(path: "api/actions/audit/\(auditId)/undo")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth(libraryPath: client.currentLibraryPath)
        if let originWindow {
            request.setValue(originWindow, forHTTPHeaderField: "X-Fichero-Origin-Window")
        }

        let session = RemoteCertificatePinning.configuredSession()
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let detail = (try? JSONDecoder().decode(ErrorResponse.self, from: data))?.detail
                ?? String(data: data, encoding: .utf8)
                ?? "Undo failed"
            invokeLogger.error("undoAction(\(auditId)) HTTP \(http.statusCode): \(detail)")
            throw APIError.httpError(statusCode: http.statusCode, message: detail)
        }

        let result = try JSONDecoder().decode(ActionInvokeResult.self, from: data)
        invokeLogger.info("undoAction(\(auditId)) ok — inverse audit \(result.auditId)")
        return result
    }

    /// Update a user's library role through the audited ACL action.
    @discardableResult
    func setLibraryRole(userId: String, role: String, originWindow: String? = nil) async throws -> ActionInvokeResult {
        try await invokeAction(
            name: "acl.set",
            params: AclSetParams(user: userId, role: role),
            originWindow: originWindow
        )
    }

    /// Revoke a user's library role (remove their access) through the same
    /// audited ACL action. Fail-closed: a role-less user is denied.
    @discardableResult
    func revokeLibraryRole(userId: String, originWindow: String? = nil) async throws -> ActionInvokeResult {
        try await invokeAction(
            name: "acl.set",
            params: AclSetParams(user: userId, remove: true),
            originWindow: originWindow
        )
    }
}

// MARK: - Wire models

/// Request envelope for `POST /api/actions/invoke`. Generic over the typed
/// params payload so call sites pass an OpenAPI schema (or any `Encodable`),
/// never a raw `[String: Any]`.
struct InvokeActionRequest<Params: Encodable>: Encodable {
    let name: String
    let params: Params
    let originWindow: String?

    enum CodingKeys: String, CodingKey {
        case name
        case params
        case originWindow = "origin_window"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encode(params, forKey: .params)
        try container.encodeIfPresent(originWindow, forKey: .originWindow)
    }
}

/// Decoded `ActionResult` from the audited choke point. `result` is free-form
/// (per-action shape) so it is intentionally not decoded here — callers that
/// need it can decode `result` separately. `auditId` feeds the undo stack.
struct ActionInvokeResult: Decodable {
    /// `ActionResult.ok` on the wire — renamed to satisfy `identifier_name`.
    let succeeded: Bool
    let auditId: String
    let changedDomains: [String]

    enum CodingKeys: String, CodingKey {
        case succeeded = "ok"
        case auditId = "audit_id"
        case changedDomains = "changed_domains"
    }
}

/// Typed params for the ACL role mutation action.
struct AclSetParams: Encodable {
    let user: String
    let role: String?
    let targetId: String?
    let effect: String?
    /// Revoke: remove the user's whole-library role. Owner-gated server-side;
    /// an owner cannot revoke their own role (fail-closed).
    let remove: Bool?

    init(
        user: String,
        role: String? = nil,
        targetId: String? = nil,
        effect: String? = nil,
        remove: Bool? = nil
    ) {
        self.user = user
        self.role = role
        self.targetId = targetId
        self.effect = effect
        self.remove = remove
    }

    enum CodingKeys: String, CodingKey {
        case user
        case role
        case targetId = "target_id"
        case effect
        case remove
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(user, forKey: .user)
        try container.encodeIfPresent(role, forKey: .role)
        try container.encodeIfPresent(targetId, forKey: .targetId)
        try container.encodeIfPresent(effect, forKey: .effect)
        try container.encodeIfPresent(remove, forKey: .remove)
    }
}

// MARK: - Last action (undo seam)

/// The most recent audited action invoked from the UI — the seed for ⌘Z (#1848).
///
/// Holds the `audit_id` returned by `/api/actions/invoke` so a future Undo
/// command can call `POST /api/actions/audit/{id}/undo`. Kept deliberately
/// small for the exhibit-A slice; per-window scoping (one holder per window,
/// injected via `@Environment`) is a follow-up — for now a single shared holder
/// records every invocation so the id is never lost.
@Observable
final class LastAction {
    /// Shared holder. Replace with per-window `@Environment(LastAction.self)`
    /// injection when the ⌘Z command surface lands.
    @MainActor static let shared = LastAction()

    /// Audit id of the last invoked action (the row `audit/{id}/undo` reverses).
    var auditId: String?
    /// Name of the last invoked action, for menu labelling ("Undo Merge").
    var actionName: String?

    init() {}

    /// Record a freshly invoked action for the undo stack.
    func record(auditId: String, actionName: String) {
        self.auditId = auditId
        self.actionName = actionName
    }
}
