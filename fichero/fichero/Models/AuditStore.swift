import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for the global audit log (#2085).
///
/// Surfaces the action-registry "who changed what" trail (#1848 / #2023 actor /
/// #2043 inverse chain) that the backend exposes at `GET /api/actions/audit`,
/// and reverses a row through `POST /api/actions/audit/{audit_id}/undo`. This is
/// the per-entity `EntityDetailView+Audit` pattern lifted to a *global* viewer:
/// one store, one networking path, the generated OpenAPI client only — no
/// hand-rolled URLs.
///
/// One instance per library (registered on `LibraryReference`), shared across
/// that library's windows. A view never calls the client directly: it reads the
/// state below and dispatches `load()` / `undo(_:)`.
@MainActor
@Observable
final class AuditStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var entries: [Components.Schemas.AuditLogEntry] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    /// The audit row currently being reversed (drives the row spinner).
    private(set) var undoingId: String?
    /// Transient result message for the most recent undo.
    private(set) var statusMessage: String?

    // ─── Transport: the generated client, used directly (the audit routes
    //     ARE in openapi.json, unlike /api/actions/invoke) ───
    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "AuditStore")

    init(client: FicheroClient) {
        self.client = client
    }

    // MARK: - Load

    /// Fetch the most recent audit rows (newest first, per the backend).
    func load(limit: Int = 100) async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let response = try await client.api.listAuditLogApiActionsAuditGet(
                query: .init(limit: limit)
            )
            switch response {
            case .ok(let okResponse):
                entries = try okResponse.body.json.items
                log.debug("Loaded \(self.entries.count, privacy: .public) audit rows")
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                loadError = detail?.detail?.description ?? "Validation error"
            case .undocumented(let statusCode, _):
                loadError = "Unexpected response (\(statusCode))"
            }
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            loadError = error.localizedDescription
            log.error("load() failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Re-fetch (post-undo / reconnect resync).
    func reload() async {
        await load()
    }

    // MARK: - Undo (maps 1:1 to the audited action layer, #1848)

    /// Reverse a recorded action by replaying its inverse. The backend writes a
    /// *new* audit row for the undo itself, so we simply reload afterwards.
    @discardableResult
    func undo(_ auditId: String) async -> Bool {
        undoingId = auditId
        defer { undoingId = nil }
        do {
            let response = try await client.api.undoActionApiActionsAuditAuditIdUndoPost(
                path: .init(auditId: auditId),
                headers: .init()
            )
            switch response {
            case .ok:
                statusMessage = "Undo complete"
                await load()
                return true
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                statusMessage = detail?.detail?.description ?? "Undo failed"
                return false
            case .undocumented(let statusCode, _):
                statusMessage = "Undo failed (\(statusCode))"
                return false
            }
        } catch {
            if error.isCancellationError { return false }   // superseded — not a failure
            statusMessage = "Undo failed"
            log.error("undo(\(auditId, privacy: .public)) failed: \(error.localizedDescription, privacy: .public)")
            return false
        }
    }

    /// Whether a row can be reversed right now: the backend marks it `undoable`
    /// and it hasn't already been undone.
    func canUndo(_ entry: Components.Schemas.AuditLogEntry) -> Bool {
        entry.undoable && !entry.undone
    }

    // MARK: - Multi-level undo (#3444)

    /// The next target for a multi-level ⌘Z that walks the audit log: the
    /// most-recent *forward* action that can still be reversed. Entries are
    /// newest-first, so this steps backward one action per undo. Rows that are
    /// themselves inverses (`inverseOf` set) are skipped — those are redo
    /// targets, not further undos — as are already-undone rows.
    var nextUndoableEntry: Components.Schemas.AuditLogEntry? {
        entries.first { $0.undoable && !$0.undone && $0.inverseOf == nil }
    }

    /// Pure walk helper (testable without the network): the newest forward,
    /// still-undoable entry in a given list.
    static func nextUndoable(
        in entries: [Components.Schemas.AuditLogEntry]
    ) -> Components.Schemas.AuditLogEntry? {
        entries.first { $0.undoable && !$0.undone && $0.inverseOf == nil }
    }

    /// Undo the most-recent still-undoable forward action, walking the audit log
    /// (#3444 multi-level undo). Loads the log first if it hasn't been fetched,
    /// so ⌘Z works without the Audit History view being open. `undo(_:)` reloads
    /// afterwards, so a repeated call naturally steps one action further back.
    @discardableResult
    func undoLast() async -> Bool {
        if entries.isEmpty { await load() }
        guard let entry = nextUndoableEntry else {
            statusMessage = "Nothing to undo"
            return false
        }
        return await undo(entry.id)
    }
}
