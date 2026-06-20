import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for the app-level user account list (#2083).
///
/// Surfaces `GET /api/auth/me` (current signed-in user) and `GET /api/users`
/// (all accounts, owner-only) through the generated OpenAPI client. A view
/// never calls the client directly — it reads `users` / `currentUser` and
/// calls `load()` once on appear.
///
/// One instance per app session, held on `AppState` (users are not library-scoped).
@MainActor
@Observable
final class UsersStore {
    private(set) var users: [Components.Schemas.UserResponse] = []
    private(set) var currentUser: Components.Schemas.UserResponse?
    private(set) var isLoading = false
    private(set) var loadError: String?

    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "UsersStore")

    init(client: FicheroClient) {
        self.client = client
    }

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        // Both requests start in parallel; /auth/me failure is non-fatal
        // (non-owner users or single-user sessions won't have a session token)
        async let meTask = client.api.meApiAuthMeGet(.init())
        async let listTask = client.api.listUsersApiUsersGet(.init())

        if let meResp = try? await meTask, case .ok(let meOk) = meResp {
            currentUser = try? meOk.body.json
        }

        do {
            let listResp = try await listTask
            if case .ok(let listOk) = listResp {
                users = try listOk.body.json.items
            }
            // Non-200 (e.g. 401 for non-owners) leaves users empty — expected
        } catch {
            loadError = error.localizedDescription
            log.error("Failed to load users: \(error.localizedDescription)")
        }
    }
}
