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
    ///   registered by the caller as a step on the window's stack (`UndoableChange`).
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
                changedDomains: json.changedDomains,
                resultId: (json.result.value as? [String: (any Sendable)?])?["id"] as? String
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
        case .notFound(let refusal):
            // Declared refusal (#5658): a sentence, plus a machine reason the window stack reads later.
            let message = (try? refusal.body.json)?.detail ?? "This step is no longer in the project's history."
            invokeLogger.error("undoAction(\(auditId)) 404: \(message)")
            throw APIError.httpError(statusCode: 404, message: message)
        case .conflict(let refusal):
            let message = (try? refusal.body.json)?.detail ?? "This step cannot be taken back now."
            invokeLogger.error("undoAction(\(auditId)) 409: \(message)")
            throw APIError.httpError(statusCode: 409, message: message)
        case .undocumented(let statusCode, _):
            invokeLogger.error("undoAction(\(auditId)) HTTP \(statusCode)")
            throw APIError.httpError(statusCode: statusCode, message: "Undo failed")
        }
    }

    /// Take back several steps together, all or none (`POST /api/actions/audit/undo`,
    /// `safety.undo.a-set-is-undone-whole`): the window's one step for a batch, or a single row
    /// as a set of one. Returns the new rows the reversal wrote; taking THOSE back is the redo.
    /// A refusal arrives as `UndoRefusal`, with the engine's sentence and its reason.
    func undoSet(auditIds: [String]) async throws -> [String] {
        let response = try await client.api.undoActionsApiActionsAuditUndoPost(body: .json(.init(auditIds: auditIds)))
        switch response {
        case .ok(let okResponse):
            let ids = try okResponse.body.json.auditIds
            invokeLogger.info("undoSet(\(auditIds.count) step(s)) ok — \(ids.count) inverse row(s)")
            return ids
        case .notFound(let refusal):
            throw UndoRefusal(try? refusal.body.json, fallback: "This change is no longer in the project's history.")
        case .conflict(let refusal):
            throw UndoRefusal(try? refusal.body.json, fallback: "This change cannot be taken back now.")
        case .unprocessableContent(let error):
            let message = (try? error.body.json)?.detail?.description ?? "Undo failed"
            invokeLogger.error("undoSet 422: \(message)")
            throw APIError.httpError(statusCode: 422, message: message)
        case .undocumented(let statusCode, _):
            invokeLogger.error("undoSet HTTP \(statusCode)")
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

    /// Share the current library with a user at a role — `POST /api/authz/share`
    /// (#3149, the "Share this library…" flow). The engine grants the recipient a
    /// per-library role through the audited `acl.set` action and returns an engine
    /// `share_url` for the object. Returns the whole response so the caller can
    /// surface that link. `object_type` is fixed to `"library"` here (no
    /// `object_id` needed); entity/document shares are a later slice.
    func shareLibrary(user: String, role: String) async throws -> Components.Schemas.ShareResponse {
        let response = try await client.api.shareLibraryObjectApiAuthzSharePost(
            body: .json(.init(user: user, role: role, objectType: "library"))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let message = (try? error.body.json)?.detail?.description ?? "Share failed"
            invokeLogger.error("shareLibrary(\(user), \(role)) 422: \(message)")
            throw APIError.httpError(statusCode: 422, message: message)
        case .undocumented(let statusCode, _):
            invokeLogger.error("shareLibrary(\(user), \(role)) HTTP \(statusCode)")
            throw APIError.httpError(statusCode: statusCode, message: "Share failed")
        }
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
    /// `result.id` when the action made or named one row (`representation.create`'s new reading) --
    /// the Reader tells the page the reading it just made, so the next run is based on it.
    var resultId: String?

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

// MARK: - An undo the engine refused (#5658)

/// The engine's answer when it will not take a step back (`UndoRefusalResponse`, 404 or 409): the
/// sentence a person reads, and why, which decides whether the window keeps the step
/// (`undo.refusal`: `changed` keeps it; `already-undone` and `gone` drop it).
struct UndoRefusal: Error, Equatable, LocalizedError {
    enum Reason: String, Equatable {
        case changed
        case alreadyUndone = "already-undone"
        case gone
        case notUndoable = "not-undoable"
    }

    let sentence: String
    let reason: Reason

    init(sentence: String, reason: Reason) {
        self.sentence = sentence
        self.reason = reason
    }

    init(_ body: Components.Schemas.UndoRefusalResponse?, fallback: String) {
        sentence = body?.detail ?? fallback
        reason = body.flatMap { Reason(rawValue: $0.reason.rawValue) } ?? .changed
    }

    /// Whether the window keeps the step on its stack after this refusal.
    var keepsTheStep: Bool { reason == .changed }

    var errorDescription: String? { sentence }
}
