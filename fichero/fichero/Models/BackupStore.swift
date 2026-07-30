import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for library backups / snapshots (#2087).
///
/// Surfaces the point-in-time snapshot trail the backend exposes under
/// `GET/POST/DELETE /api/storage/snapshots` (create / list / restore / delete),
/// backed by `fichero-server/storage_snapshots.py`. Mirrors `AuditStore`: one
/// store per library (registered on `LibraryReference`), the generated OpenAPI
/// client only — no hand-rolled URLs.
///
/// A view never calls the client directly: it reads the state below and
/// dispatches `load()` / `create(reason:)` / `restore(_:)` / `delete(_:)`.
///
/// ponytail: holds `Components.Schemas.LibrarySnapshot` directly (no mirror
/// struct) and lists ALL snapshots (no `library_name` filter) — the simplest
/// thing that shows the backups. There is no schedule endpoint to drive a
/// schedule control, so the UI omits scheduling; the only background snapshotter
/// is the engine's internal periodic task (`start_periodic_snapshot_task`),
/// which is not user-configurable over HTTP.
@MainActor
@Observable
final class BackupStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var snapshots: [Components.Schemas.LibrarySnapshot] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    /// True while a snapshot is being created (drives the Create button spinner).
    private(set) var isCreating = false
    /// The snapshot currently being restored (drives the row spinner).
    private(set) var restoringId: String?
    /// The snapshot currently being deleted (drives the row spinner).
    private(set) var deletingId: String?
    /// Transient result message for the most recent create / restore / delete.
    private(set) var statusMessage: String?

    // ─── Transport: the generated client, used directly (the snapshot routes
    //     ARE in openapi.json) ───
    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "BackupStore")

    init(client: FicheroClient) {
        self.client = client
    }

    // MARK: - Load

    /// Fetch all snapshots (newest first, per the backend).
    func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let response = try await client.api.getSnapshotsApiStorageSnapshotsGet(
                query: .init(includeExpired: false)
            )
            switch response {
            case .ok(let okResponse):
                snapshots = try okResponse.body.json.snapshots
                log.debug("Loaded \(self.snapshots.count, privacy: .public) snapshots")
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

    // MARK: - Create

    /// Create a point-in-time snapshot of the current library. The backend writes
    /// a new snapshot row, so we reload afterwards.
    @discardableResult
    func create(reason: String = "") async -> Bool {
        guard let libraryPath = client.currentLibraryPath, !libraryPath.isEmpty else {
            statusMessage = "No library open"
            return false
        }
        isCreating = true
        defer { isCreating = false }
        do {
            let response = try await client.api.createSnapshotApiStorageSnapshotsPost(
                query: .init(libraryPath: libraryPath, reason: reason)
            )
            switch response {
            case .ok:
                statusMessage = "Snapshot created"
                await load()
                return true
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                statusMessage = detail?.detail?.description ?? "Create failed"
                return false
            case .undocumented(let statusCode, _):
                statusMessage = "Create failed (\(statusCode))"
                return false
            }
        } catch {
            if error.isCancellationError { return false }   // superseded — not a failure
            statusMessage = "Create failed"
            log.error("create() failed: \(error.localizedDescription, privacy: .public)")
            return false
        }
    }

    // MARK: - Restore (destructive — overwrites the live library)

    /// Restore a snapshot into its original library package. Destructive: the
    /// live DuckDB / LanceDB are overwritten (the backend keeps a backup copy).
    @discardableResult
    func restore(_ snapshotId: String) async -> Bool {
        restoringId = snapshotId
        defer { restoringId = nil }
        do {
            let response = try await client.api.restoreLibrarySnapshotApiStorageSnapshotsSnapshotIdRestorePost(
                path: .init(snapshotId: snapshotId)
            )
            switch response {
            case .ok(let okResponse):
                let result = try okResponse.body.json
                statusMessage = result.note
                return true
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                statusMessage = detail?.detail?.description ?? "Restore failed"
                return false
            case .undocumented(let statusCode, _):
                statusMessage = "Restore failed (\(statusCode))"
                return false
            }
        } catch {
            if error.isCancellationError { return false }   // superseded — not a failure
            statusMessage = "Restore failed"
            log.error(
                "restore(\(snapshotId, privacy: .public)) failed: \(error.localizedDescription, privacy: .public)"
            )
            return false
        }
    }

    // MARK: - Delete

    /// Delete a snapshot and its data files. Reloads on success.
    @discardableResult
    func delete(_ snapshotId: String) async -> Bool {
        deletingId = snapshotId
        defer { deletingId = nil }
        do {
            let response = try await client.api.removeSnapshotApiStorageSnapshotsSnapshotIdDelete(
                path: .init(snapshotId: snapshotId)
            )
            switch response {
            case .ok:
                statusMessage = "Snapshot deleted"
                await load()
                return true
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                statusMessage = detail?.detail?.description ?? "Delete failed"
                return false
            case .undocumented(let statusCode, _):
                statusMessage = "Delete failed (\(statusCode))"
                return false
            }
        } catch {
            if error.isCancellationError { return false }   // superseded — not a failure
            statusMessage = "Delete failed"
            log.error("delete(\(snapshotId, privacy: .public)) failed: \(error.localizedDescription, privacy: .public)")
            return false
        }
    }
}
