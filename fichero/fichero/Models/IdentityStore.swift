import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable "who am I on this engine?" store (F5).
///
/// Surfaces `GET /api/auth/identity` — the one endpoint that answers, across all
/// auth modes, three questions the access UX needs: is multi-user on, which
/// credential kind am I using, and does this access resolve to the owner / a
/// named user. This is distinct from `UsersStore` (the account *list* + create/
/// disable) and `SessionStore` (the login *gate* + login/logout): those own
/// mutation and the sign-in flow; this is a read-only identity probe the
/// access-denied and connection views read to phrase "you are X, and that's why
/// this is blocked". Login/logout is NOT duplicated here — callers drive
/// `SessionStore` for that.
///
/// One instance per app session, held on `AppState`.
@MainActor
@Observable
final class IdentityStore {
    private(set) var identity: Components.Schemas.AuthIdentityResponse?
    /// Set when the last `load()` failed, typed so the UI can react (e.g. an
    /// `.unauthenticated` identity probe means "not signed in", a
    /// `.tlsPinFailure` means "reset pin"). Cleared on the next attempt.
    private(set) var loadError: AccessError?
    private(set) var isLoading = false

    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "IdentityStore")

    init(client: FicheroClient) {
        self.client = client
    }

    // MARK: - Derived

    var multiuserEnabled: Bool { identity?.multiuserEnabled ?? false }
    var isOwnerAccess: Bool { identity?.isOwnerAccess ?? false }
    var authKind: String? { identity?.authKind }
    var user: Components.Schemas.AuthIdentityUser? { identity?.user }

    /// The signed-in display name, or nil when the credential doesn't resolve to
    /// a named user (single-user / bootstrap token).
    var displayName: String? { identity?.user?.displayName ?? identity?.user?.username }

    /// Authenticated when a user resolves, or when multi-user is off (the
    /// bootstrap token is always owner-capable). A `nil` identity means "not yet
    /// probed / probe failed" — deliberately NOT authenticated (fail closed).
    var isAuthenticated: Bool {
        guard let identity else { return false }
        return identity.user != nil || !identity.multiuserEnabled
    }

    // MARK: - Load

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            let response = try await client.api.identityApiAuthIdentityGet()
            switch response {
            case .ok(let okResponse):
                identity = try okResponse.body.json
            case .undocumented(let statusCode, _):
                identity = nil
                loadError = AccessError.classify(statusCode: statusCode, body: nil)
                    ?? .transport("Identity probe returned \(statusCode).")
                log.error("Identity probe returned \(statusCode)")
            }
        } catch {
            if error.isCancellationError { return }   // superseded — keep identity, no error state
            identity = nil
            loadError = AccessError.classify(error)
            log.error("Identity probe failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    #if DEBUG
    /// Test seam: seed a decoded identity without a live engine, so the derived
    /// `isAuthenticated` / `isOwnerAccess` / `displayName` logic is unit-testable.
    func setIdentityForTesting(_ identity: Components.Schemas.AuthIdentityResponse?) {
        self.identity = identity
    }
    #endif
}
