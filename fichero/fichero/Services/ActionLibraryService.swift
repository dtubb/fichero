import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

/// Canonical service for the Action Library (`/api/actions`).
///
/// Routes every REST call through the generated OpenAPI client
/// (`FicheroClient` → `AuthTokenMiddleware` + `LibraryPathMiddleware`) instead
/// of hand-written `URLSession` requests (#1666/#1711). This is the single
/// transport for all `/api/actions/*` traffic: the former two duplicate
/// services (`ActionsService` + `ActionLibraryService`) both spoke raw
/// `URLRequest` to the same surface; they are now collapsed onto this one type,
/// with `ActionsService` reduced to a thin subclass that only carries the
/// label/return-shape variants its existing call sites depend on.
///
/// Production callers inject the library's real generated client; previews create
/// an explicit client through `EngineConfig.transportMode`. `LibraryPathMiddleware`
/// injects `X-Fichero-Library-Path` centrally for library-scoped paths (#1710).
@MainActor
@Observable
class ActionLibraryService {
    let logger = Logger(subsystem: "app.fichero.fichero", category: "ActionLibraryService")

    var actions: [ActionItem] = []
    var categories: [String] = []
    var recentActions: [ActionItem] = []
    var popularActions: [ActionItem] = []
    var isLoading = false
    var error: String?

    /// Shared generated client — the single transport for both this type and the
    /// `ActionsService` subclass.
    let client: FicheroClient

    /// Per-library holder for the most-recent audited action, powering ⌘Z
    /// (#3444). Scoped to this service (one per library) — NOT a process-global
    /// singleton, so an undo can't reverse a different library's action. The
    /// `invokeAction` central seam records every audited mutation here.
    let lastAction = LastAction()

    /// - Parameter client: The generated client to route `/api/actions/*` through.
    ///   Required (no default): production injects the library's real client via
    ///   `LibraryManager` (which honors `EngineConfig.transportMode` — UDS /
    ///   in-process / HTTPS). A localhost default here would silently pin every
    ///   accidental no-arg construction to HTTPS `127.0.0.1:8765`, which fails with
    ///   a bare `-1004` under an embedded (UDS) engine.
    init(client: FicheroClient) {
        self.client = client
    }

    /// Create a new action. Declared in the class body (NOT an extension) because
    /// the `ActionsService` subclass overrides it — Swift forbids overriding a
    /// method declared in an extension (static dispatch).
    func createAction(_ action: CreateActionRequest) async throws -> ActionItem {
        let response = try await client.api.createActionApiActionsPost(
            body: .json(.init(
                name: action.name,
                description: action.description,
                category: action.category,
                tags: action.tags,
                icon: action.icon,
                author: action.author
            ))
        )
        switch response {
        case .ok(let okResponse):
            let created: ActionItem = try decodeModel(from: try okResponse.body.json)
            logger.info("Created action: \(created.name)")
            return created
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }
}

// ActionItem and CreateActionRequest are defined in ActionsService.swift — do not duplicate
