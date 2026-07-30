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

    /// True when `GET /api/users` came back 401/403 — the caller is signed in but
    /// isn't the library owner (the list is owner-only). Lets the view say "you
    /// don't manage accounts" instead of the misleading "No accounts" (#3287).
    private(set) var listAccessDenied = false

    /// Pending (unredeemed, unexpired) account invites, owner-only (#3157).
    private(set) var invites: [Components.Schemas.InviteResponse] = []

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
            switch listResp {
            case .ok(let listOk):
                users = try listOk.body.json.items
                listAccessDenied = false
            case .undocumented(let statusCode, _):
                // Owner-only endpoint: 401/403 for a signed-in non-owner is
                // "not permitted", not "no accounts" (#3287). Other non-2xx codes
                // are genuine load failures.
                listAccessDenied = (statusCode == 401 || statusCode == 403)
                if listAccessDenied {
                    users = []
                }
            }
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            loadError = error.localizedDescription
            log.error("Failed to load users: \(error.localizedDescription)")
        }
    }

    /// Create an account (owner-only on the engine). Reloads the list on success.
    /// Throws `UsersStoreError` with the engine's message on 4xx so the caller
    /// can surface it (e.g. 409 "username already exists").
    func createUser(
        username: String,
        displayName: String,
        password: String,
        isOwner: Bool
    ) async throws {
        let response = try await client.api.createUserApiUsersPost(
            body: .json(.init(
                username: username,
                displayName: displayName,
                password: password,
                isOwner: isOwner
            ))
        )
        guard case .ok = response else {
            throw Self.error(from: response)
        }
        await reload()
    }

    /// Enable/disable an account (owner-only). Disabling also revokes the
    /// account's sessions server-side. Reloads the list on success.
    func setActive(userId: String, active: Bool) async throws {
        let response = try await client.api.updateUserApiUsersUserIdPatch(
            .init(
                path: .init(userId: userId),
                body: .json(.init(active: active))
            )
        )
        guard case .ok = response else {
            throw Self.error(from: response)
        }
        await reload()
    }

    // MARK: - Invites (#3157)

    /// Load pending account invites (owner-only). Non-fatal: a non-200 (e.g. a
    /// non-owner or multi-user off) leaves the list empty rather than erroring.
    func loadInvites() async {
        do {
            let response = try await client.api.listInvitesApiAuthInvitesGet()
            if case .ok(let okResponse) = response {
                invites = try okResponse.body.json.items
            } else {
                invites = []
            }
        } catch {
            if error.isCancellationError { return }   // superseded — keep current invites, no log
            invites = []
            log.error("Failed to load invites: \(error.localizedDescription)")
        }
    }

    /// Mint an invite (owner-only). Returns the mint payload (invite + token +
    /// `fichero://invite?token=…` redemption URL) so the caller can present the
    /// link/QR to hand over. Reloads the pending list on success.
    func createInvite(username: String, displayName: String?) async throws
        -> Components.Schemas.InviteMintResponse {
        let response = try await client.api.createInviteApiAuthInvitesPost(
            body: .json(.init(username: username, displayName: displayName))
        )
        guard case .ok(let okResponse) = response else {
            throw Self.error(from: response)
        }
        let mint = try okResponse.body.json
        await loadInvites()
        return mint
    }

    /// Revoke a pending invite by id (owner-only). Reloads the list on success.
    func revokeInvite(id: String) async throws {
        let response = try await client.api.revokeInviteApiAuthInvitesInviteIdRevokePost(
            .init(path: .init(inviteId: id))
        )
        guard case .ok = response else {
            throw Self.error(from: response)
        }
        await loadInvites()
    }

    /// Force a reload even while a prior load is settling (mutations bypass the
    /// `isLoading` guard `load()` uses to dedupe concurrent view appearances).
    private func reload() async {
        isLoading = false
        await load()
    }

    private static func error(from response: some Sendable) -> UsersStoreError {
        UsersStoreError(message: "\(response)")
    }
}

struct UsersStoreError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
