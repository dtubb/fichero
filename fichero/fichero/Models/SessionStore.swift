import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable auth/session state for multi-user login (EPIC #2021/#2022).
///
/// When the engine runs with `FICHERO_MULTIUSER=1` a *remote* request needs a
/// logged-in session (identity + per-library role). A **loopback** request
/// bearing the bootstrap `.api-key` does not: the engine treats that shared
/// secret as a standing owner-capable superuser regardless of multi-user state,
/// because any process that can read the 0600 file is already the Mac's owner
/// (see `fichero/api/auth.py`). This store drives the login gate:
///
/// - `refresh()` probes `GET /api/auth/me` on launch to restore a session.
///   404 means the backend has multi-user turned off (no gate at all); 200
///   means a stored session is still valid. A 401 does NOT imply a wall — the
///   bootstrap credential is *deliberately* 401'd by `/auth/me`, which reports
///   the session user and has none. `GET /api/auth/identity` is the authority:
///   its `is_owner_access` answers "is this caller the owner?" directly, and
///   only when that is false does a `GET /api/users` probe decide between the
///   first-run "create owner" screen and normal login.
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

    /// Set when the app opens a `fichero://invite?token=…` link (#3157). While
    /// non-nil the auth gate shows the redeem-invite screen (set-your-password),
    /// regardless of `phase`, so even a signed-in user can redeem into a new
    /// account. Cleared on success or cancel. The token is a secret and is never
    /// logged.
    private(set) var pendingInviteToken: String?

    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "SessionStore")

    init(client: FicheroClient) {
        self.client = client
    }

    /// The engine host this store gates, as the middleware sees it. Session
    /// tokens are Keychain-scoped per host (#3150) exactly like the device
    /// token, so this store persists/reads/clears under its OWN client's host —
    /// never the single global default. That lets the app hold a local-library
    /// session AND a remote engine's session at once (each store keyed to its
    /// client's host). `AuthTokenMiddleware.intercept` reads the session token
    /// off `baseURL.absoluteString`, so keying off the same string here makes
    /// persist and read resolve to the same account after normalization.
    private var hostString: String { client.baseURL.absoluteString }

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
            // 401 (no/expired session) or an inconclusive probe. Ask
            // `/api/auth/identity` (#3819): it reports whether multi-user is on
            // AND whether the credential already resolves to a user. The engine
            // bootstraps the local owner automatically, so on a fresh
            // single-user install identity returns that owner under
            // `auth_kind == "bootstrap"` even though `/auth/me` 401s — proceed
            // as that owner, never a create-user wall. (When multi-user is OFF
            // the credential is likewise sufficient, #3330.)
            let identity = await identity()
            let multiuserEnabled = identity?.multiuserEnabled
            let identityUserResolved = identity?.user != nil
            let isOwnerAccess = identity?.isOwnerAccess ?? false
            // The account-count probe only decides the owner-setup/login split,
            // so skip it once the credential already resolves to an owner.
            let accountsExist =
                (identityUserResolved || isOwnerAccess) ? nil : await accountsExist()
            phase = Self.resolvePhase(
                meStatusCode: meCode,
                accountsExist: accountsExist,
                multiuserEnabled: multiuserEnabled,
                identityUserResolved: identityUserResolved,
                isOwnerAccess: isOwnerAccess
            )
            if phase != .authenticated { currentUser = nil }
        }
    }

    /// Pure decision used by `refresh()`, extracted so the gate logic is
    /// unit-testable without a live engine. `accountsExist` is `nil` when the
    /// account-count probe could not be resolved (e.g. a remote engine where
    /// the bootstrap path isn't available) — in that case we fail closed to the
    /// login screen rather than assuming a fresh install.
    ///
    /// `isOwnerAccess` mirrors `GET /api/auth/identity`'s `is_owner_access`: the
    /// engine's own verdict that this credential is the owner. It is true for
    /// `auth_kind == "bootstrap"` — the loopback-only, same-Mac, 0600 `.api-key`
    /// — which the engine treats as a standing superuser whether or not
    /// multi-user is on. The Mac running the engine is the owner; it must never
    /// see a login wall, or there is no way to reach Settings to configure the
    /// very accounts the wall demands (#3941).
    ///
    /// `identityUserResolved` (#3819) is kept for the session case but CANNOT
    /// carry the bootstrap one: `auth.py` populates `request.state.user` from
    /// `_resolve_single_user_owner()` only when multi-user is OFF, and pins it
    /// to `None` on the multi-user bootstrap path — so `identity.user` is
    /// structurally always null there and this flag never fires.
    ///
    /// Neither flag is load-bearing for library access: with multi-user ON and
    /// the bootstrap token, `/api/documents`, `/api/entities`, `/api/activity`
    /// and `/api/authz/library` all return 200. The wall gated access the engine
    /// had already granted.
    nonisolated static func resolvePhase(
        meStatusCode: Int,
        accountsExist: Bool?,
        multiuserEnabled: Bool? = nil,
        identityUserResolved: Bool = false,
        isOwnerAccess: Bool = false
    ) -> Phase {
        switch meStatusCode {
        case 200: return .authenticated
        case 404: return .disabled
        case _ where multiuserEnabled == false: return .disabled
        case _ where isOwnerAccess: return .disabled
        case _ where identityUserResolved: return .disabled
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
            try AuthTokenMiddleware.persistSessionToken(payload.sessionToken, hostString: hostString)
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
        let displayName = Self.ownerDisplayName(displayName, username: username)
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

    nonisolated static func ownerDisplayName(_ displayName: String, username: String) -> String {
        let trimmedDisplayName = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmedDisplayName.isEmpty { return trimmedDisplayName }
        return username.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Invite redemption (#3157)

    /// Extract the invite token from a `fichero://invite?token=…` deep link, or
    /// `nil` if the URL isn't a well-formed invite link. Pure + `nonisolated` so
    /// both the macOS and iOS `onOpenURL` handlers share one parser and it's
    /// unit-testable. The token itself is a secret and is never logged.
    nonisolated static func inviteToken(from url: URL) -> String? {
        guard url.scheme?.lowercased() == "fichero",
              url.host?.lowercased() == "invite",
              let token = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                  .queryItems?.first(where: { $0.name == "token" })?.value,
              !token.isEmpty
        else { return nil }
        return token
    }

    /// Begin redeeming an invite opened from a `fichero://invite?token=…` link.
    /// Surfaces the redeem screen through the gate; the token is held only in
    /// memory until the invitee sets a password.
    func beginInviteRedemption(token: String) {
        pendingInviteToken = token
    }

    /// Dismiss the redeem screen without redeeming (returns to the prior gate).
    func cancelInviteRedemption() {
        pendingInviteToken = nil
    }

    /// Redeem the pending invite with the password the invitee chooses. On
    /// success the engine returns a session (identical to login), which is
    /// persisted to the Keychain and drops the invitee straight into a
    /// signed-in session.
    func redeemInvite(newPassword: String) async throws {
        guard let token = pendingInviteToken else { throw AuthError.invalidInput }
        let request = Components.Schemas.InviteRedeemRequest(
            inviteToken: token,
            newPassword: newPassword
        )
        let response = try await client.api.redeemInviteApiAuthInvitesRedeemPost(body: .json(request))
        switch response {
        case .ok(let ok):
            let payload = try ok.body.json
            try AuthTokenMiddleware.persistSessionToken(payload.sessionToken, hostString: hostString)
            currentUser = payload.user
            pendingInviteToken = nil
            phase = .authenticated
            log.info("Redeemed invite, signed in as \(payload.user.username, privacy: .public)")
        case .unprocessableContent:
            throw AuthError.invalidInput
        case .undocumented(let statusCode, _):
            throw AuthError.redeemInvite(statusCode: statusCode)
        }
    }

    func logout() async {
        // Best-effort server-side revoke; clear local state regardless.
        _ = try? await client.api.logoutApiAuthLogoutPost()
        AuthTokenMiddleware.clearSessionToken(hostString: hostString)
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
                return try !ok.body.json.items.isEmpty
            case .undocumented:
                return nil
            }
        } catch {
            return nil
        }
    }

    /// `GET /api/auth/identity` — reports multi-user state AND, when the
    /// credential resolves to a user (including the auto-bootstrapped local
    /// owner), that user. `nil` when the probe couldn't be resolved. See
    /// `resolvePhase` for how the result gates first-run (#3819).
    private func identity() async -> Components.Schemas.AuthIdentityResponse? {
        do {
            let response = try await client.api.identityApiAuthIdentityGet()
            switch response {
            case .ok(let ok):
                return try ok.body.json
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
    case redeemInvite(statusCode: Int)

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
        case .redeemInvite(let statusCode):
            switch statusCode {
            case 401: return "This invite has expired or was already used. Ask for a new one."
            case 409: return "That account already exists. Sign in instead."
            case 404: return "Multi-user login is not enabled on this server."
            case 429: return "Too many attempts. Wait a moment and try again."
            default: return "Could not redeem the invite (error \(statusCode))."
            }
        }
    }
}
