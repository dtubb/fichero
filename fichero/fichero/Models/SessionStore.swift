import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable auth/session state for multi-user login (EPIC #2021/#2022).
///
/// When the engine runs with `FICHERO_MULTIUSER=1` every library request needs
/// a logged-in *session* (identity + per-library role). The bootstrap `.api-key`
/// is owner-capable for admin endpoints but carries no user, so without a
/// session the library 401/403s. This store drives the login gate:
///
/// - `refresh()` probes `GET /api/auth/me` on launch to restore a session.
///   404 means the backend has multi-user turned off (no gate at all); 200
///   means a stored session is still valid; 401 means we must sign in — and a
///   secondary `GET /api/users` probe (allowed under the loopback bootstrap
///   token) decides between the first-run "create owner" screen and normal login.
/// - `login` / `createOwner` mint a session token, stored in the **Keychain**
///   via `AuthTokenMiddleware` so every subsequent request carries it.
/// - `logout` revokes the server session and clears the Keychain.
///
/// SECURITY: passwords and tokens are never logged. Probe/derivation failures
/// fail closed (default to requiring login rather than silently proceeding).
///
/// One instance per app session, held on `AppState`.
@MainActor
@Observable
final class SessionStore {
    enum Phase: Equatable {
        /// Still probing on launch — show a spinner, not the library.
        case checking
        /// Multi-user auth is disabled on the backend; no login gate.
        case disabled
        /// Multi-user on, no accounts exist yet — show "create owner".
        case needsOwnerSetup
        /// Multi-user on, accounts exist, but no valid session — show login.
        case needsLogin
        /// A valid session is present; the library may load.
        case authenticated
    }

    private(set) var phase: Phase = .checking
    private(set) var currentUser: Components.Schemas.UserResponse?

    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "SessionStore")

    init(client: FicheroClient) {
        self.client = client
    }

    /// True once the gate has resolved and the library should be shown.
    var allowsLibraryAccess: Bool {
        switch phase {
        case .disabled, .authenticated: return true
        case .checking, .needsLogin, .needsOwnerSetup: return false
        }
    }

    // MARK: - Launch probe / session restore

    func refresh() async {
        phase = .checking
        let meCode = await meStatusCode()
        switch meCode {
        case 200:
            phase = .authenticated
        case 404:
            // Backend has multi-user auth disabled — never gate.
            currentUser = nil
            phase = .disabled
        default:
            // 401 (no/expired session) or an inconclusive probe: decide between
            // first-run owner setup and normal login using the account count.
            let accountsExist = await accountsExist()
            phase = Self.resolvePhase(meStatusCode: meCode, accountsExist: accountsExist)
            if phase != .authenticated { currentUser = nil }
        }
    }

    /// Pure decision used by `refresh()`, extracted so the gate logic is
    /// unit-testable without a live engine. `accountsExist` is `nil` when the
    /// account-count probe could not be resolved (e.g. a remote engine where
    /// the bootstrap path isn't available) — in that case we fail closed to the
    /// login screen rather than assuming a fresh install.
    nonisolated static func resolvePhase(meStatusCode: Int, accountsExist: Bool?) -> Phase {
        switch meStatusCode {
        case 200: return .authenticated
        case 404: return .disabled
        default: return accountsExist == false ? .needsOwnerSetup : .needsLogin
        }
    }

    // MARK: - Actions

    func login(username: String, password: String) async throws {
        let request = Components.Schemas.LoginRequest(
            username: username,
            password: password,
            deviceLabel: Self.deviceLabel
        )
        let response = try await client.api.loginApiAuthLoginPost(body: .json(request))
        switch response {
        case .ok(let ok):
            let payload = try ok.body.json
            try AuthTokenMiddleware.persistSessionToken(payload.sessionToken)
            currentUser = payload.user
            phase = .authenticated
            log.info("Signed in as \(payload.user.username, privacy: .public)")
        case .unprocessableContent:
            throw AuthError.invalidInput
        case .undocumented(let statusCode, _):
            throw AuthError.login(statusCode: statusCode)
        }
    }

    /// First-run: create the initial owner account (bootstrap-authed on the
    /// loopback path — the middleware attaches the bootstrap token because no
    /// session exists yet), then sign in as that owner.
    func createOwner(username: String, displayName: String, password: String) async throws {
        let request = Components.Schemas.CreateUserRequest(
            username: username,
            displayName: displayName,
            password: password,
            isOwner: true
        )
        let response = try await client.api.createUserApiUsersPost(body: .json(request))
        switch response {
        case .ok:
            try await login(username: username, password: password)
        case .unprocessableContent:
            throw AuthError.invalidInput
        case .undocumented(let statusCode, _):
            throw AuthError.createOwner(statusCode: statusCode)
        }
    }

    func logout() async {
        // Best-effort server-side revoke; clear local state regardless.
        _ = try? await client.api.logoutApiAuthLogoutPost()
        AuthTokenMiddleware.clearSessionToken()
        currentUser = nil
        phase = .needsLogin
    }

    // MARK: - Probes

    private func meStatusCode() async -> Int {
        do {
            let response = try await client.api.meApiAuthMeGet()
            switch response {
            case .ok(let ok):
                currentUser = try? ok.body.json
                return 200
            case .undocumented(let statusCode, _):
                return statusCode
            }
        } catch {
            // Network/decoding failure — fail closed to "needs login".
            return -1
        }
    }

    /// `true` if at least one account exists, `false` if zero, `nil` if the
    /// probe couldn't determine it (non-200 — e.g. no bootstrap on a remote host).
    private func accountsExist() async -> Bool? {
        do {
            let response = try await client.api.listUsersApiUsersGet()
            switch response {
            case .ok(let ok):
                return try ok.body.json.count > 0
            case .undocumented:
                return nil
            }
        } catch {
            return nil
        }
    }

    private static var deviceLabel: String {
        let name = ProcessInfo.processInfo.hostName.trimmingCharacters(in: .whitespacesAndNewlines)
        return name.isEmpty ? "Fichero" : name
    }
}

/// User-facing auth errors. Messages never include the submitted password or
/// any token — only the failure category.
enum AuthError: LocalizedError, Equatable {
    case invalidInput
    case login(statusCode: Int)
    case createOwner(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidInput:
            return "Please enter a valid username and password."
        case .login(let statusCode):
            switch statusCode {
            case 401: return "Incorrect username or password."
            case 403: return "This account is disabled. Ask an owner to re-enable it."
            case 404: return "Multi-user login is not enabled on this server."
            case 429: return "Too many attempts. Wait a moment and try again."
            default: return "Sign-in failed (error \(statusCode))."
            }
        case .createOwner(let statusCode):
            switch statusCode {
            case 403: return "Owner setup must run on the same Mac as the engine."
            case 409: return "That username is already taken."
            case 404: return "Multi-user login is not enabled on this server."
            default: return "Could not create the owner account (error \(statusCode))."
            }
        }
    }
}
