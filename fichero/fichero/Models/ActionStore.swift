import Foundation
import Observation
import OSLog

/// Observable domain store for the Action Library (#1905, mirrors `NoteStore`).
///
/// The single endpoint accessor for action-library data. A view never calls
/// `ActionsService` directly: it observes the state below and dispatches the
/// named actions. Each action performs the typed write and then refreshes state
/// — today via an explicit reload, and via `apply(_:)` once the per-library
/// change-stream starts emitting `action.*` events. Swapping reload for push
/// is then a no-op at every call site.
///
/// One instance per library (registered on `LibraryReference`), shared across
/// that library's windows.
@MainActor
@Observable
final class ActionStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var actions: [ActionItem] = []
    private(set) var categories: [String] = []
    private(set) var recentActions: [ActionItem] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    /// Monotonic counter bumped on every applied `action.*` change event.
    private(set) var changeToken: Int = 0

    // ─── Transport: the EXISTING ActionsService wrapper, unchanged ───
    /// Accessible (not private) as a transitional seam: `ActionDetailView`
    /// still accepts `service: ActionsService` directly and will be updated
    /// to use the store in a follow-up PR.
    let actionsService: ActionsService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ActionStore")

    init(service: ActionsService) {
        self.actionsService = service
    }

    // MARK: - Load (the store, not the view, owns fetching)

    func loadActions() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        await actionsService.loadActions()
        actions = actionsService.actions
        loadError = actionsService.error
        log.debug("Loaded \(self.actions.count, privacy: .public) actions")
    }

    func loadCategories() async {
        await actionsService.loadCategories()
        categories = actionsService.categories
    }

    func loadRecentActions(limit: Int = 10) async {
        await actionsService.loadRecentActions(limit: limit)
        recentActions = actionsService.recentActions
    }

    func loadBuiltinActions() async -> [ActionItem] {
        await actionsService.loadBuiltinActions()
    }

    func loadCustomActions() async -> [ActionItem] {
        await actionsService.loadCustomActions()
    }

    func loadPopularActions(limit: Int = 10) async -> [ActionItem] {
        await actionsService.loadPopularActions(limit: limit)
    }

    /// Re-fetch actions (post-mutation / reconnect resync).
    func reload() async {
        await loadActions()
    }

    // MARK: - Named actions (map 1:1 to the audited action layer, #1848)

    @discardableResult
    func createAction(_ request: CreateActionRequest) async throws -> ActionItem {
        let item = try await actionsService.createAction(request)
        actions = actionsService.actions
        return item
    }

    func deleteAction(id: String) async throws {
        try await actionsService.deleteAction(id: id)
        actions = actionsService.actions
    }

    @discardableResult
    func importAction(json: String) async throws -> ActionItem {
        let item = try await actionsService.importAction(json: json)
        actions = actionsService.actions
        return item
    }

    func recordUse(_ actionId: String) async {
        await actionsService.recordUse(actionId: actionId)
    }

    func exportAction(id: String) async throws -> String {
        try await actionsService.exportAction(id: id)
    }

    // MARK: - ChangeEventConsumer (called by LibraryChangeStream, NOT by views)

    nonisolated var changeDomain: String { "action" }

    func apply(_ event: ChangeEvent) {
        changeToken &+= 1
        switch event.verb {
        case "created", "updated", "deleted":
            scheduleReload()
        default:
            break
        }
    }

    /// Holds the shared 300ms trailing-reload debouncer (#1973). `scheduleReload()`
    /// (called above for create/update/delete) and `resync()` are provided by the
    /// `ObservableDomainStore` extension — no per-store copies.
    let reloadDebouncer = ReloadDebouncer()
}
