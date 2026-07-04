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
/// `/api/actions/invoke` (and its undo sibling `/api/actions/audit/{id}/undo`)
/// are now in `openapi.json`, so these route through the generated
/// `FicheroClient` like the rest of `/api/actions/*` (#3029). The generated
/// `LibraryPathMiddleware` injects `X-Fichero-Library-Path` centrally; the
/// origin-window de-dup header is a typed op header. Params are still typed at
/// the call site (`Components.Schemas.EntityMergeRequest`, `AclSetParams`, …)
/// and bridged into the op's free-form `params` container via a JSON round-trip.
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
        let request = Components.Schemas.InvokeActionRequest(
            name: name,
            params: try Self.paramsPayload(params),
            originWindow: originWindow
        )
        let response = try await client.api.invokeActionApiActionsInvokePost(.init(
            headers: .init(xFicheroOriginWindow: originWindow),
            body: .json(request)
        ))
        switch response {
        case .ok(let okResponse):
            let json = try okResponse.body.json
            let result = ActionInvokeResult(
                succeeded: json.ok,
                auditId: json.auditId,
                changedDomains: json.changedDomains
            )
            invokeLogger.info("invokeAction(\(name)) ok — audit \(result.auditId)")
            return result
        case .unprocessableContent(let error):
            // Surface the FastAPI `detail` string, matching the generated
            // services' validation-error mapping.
            let message = (try? error.body.json)?.detail?.description ?? "Action failed"
            invokeLogger.error("invokeAction(\(name)) 422: \(message)")
            throw APIError.httpError(statusCode: 422, message: message)
        case .undocumented(let statusCode, _):
            invokeLogger.error("invokeAction(\(name)) HTTP \(statusCode)")
            throw APIError.httpError(statusCode: statusCode, message: "Action failed")
        }
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
        let response = try await client.api.undoActionApiActionsAuditAuditIdUndoPost(.init(
            path: .init(auditId: auditId),
            headers: .init(xFicheroOriginWindow: originWindow)
        ))
        switch response {
        case .ok(let okResponse):
            let json = try okResponse.body.json
            let result = ActionInvokeResult(
                succeeded: json.ok,
                auditId: json.auditId,
                changedDomains: json.changedDomains
            )
            invokeLogger.info("undoAction(\(auditId)) ok — inverse audit \(result.auditId)")
            return result
        case .unprocessableContent(let error):
            let message = (try? error.body.json)?.detail?.description ?? "Undo failed"
            invokeLogger.error("undoAction(\(auditId)) 422: \(message)")
            throw APIError.httpError(statusCode: 422, message: message)
        case .undocumented(let statusCode, _):
            invokeLogger.error("undoAction(\(auditId)) HTTP \(statusCode)")
            throw APIError.httpError(statusCode: statusCode, message: "Undo failed")
        }
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

// MARK: - Params bridge

extension ActionLibraryService {
    /// Bridge a typed `Encodable` params value into the generated op's free-form
    /// `params` container. Call sites stay typed (`EntityMergeRequest`,
    /// `AclSetParams`, …) while the wire shape matches the backend's `Raw action
    /// params` object. A JSON round-trip is the cleanest typed→container
    /// conversion: `ParamsPayload.init(from:)` slurps object keys into
    /// `additionalProperties`.
    static func paramsPayload<Params: Encodable>(
        _ params: Params
    ) throws -> Components.Schemas.InvokeActionRequest.ParamsPayload {
        let data = try JSONEncoder().encode(params)
        return try JSONDecoder().decode(
            Components.Schemas.InvokeActionRequest.ParamsPayload.self,
            from: data
        )
    }
}

// MARK: - Wire models

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
