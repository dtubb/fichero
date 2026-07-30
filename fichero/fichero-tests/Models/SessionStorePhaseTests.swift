@testable import Fichero
import Foundation
import Testing

/// Unit tests for the multi-user login gate's pure decision logic (#2021/#2022).
/// `SessionStore.resolvePhase` maps a `/api/auth/me` status + account-count
/// probe onto the gate phase without a live engine.
@Suite("Session gate phase resolution")
struct SessionStorePhaseTests {
    @Test("a valid session (me == 200) authenticates regardless of account count")
    func validSessionAuthenticates() {
        #expect(SessionStore.resolvePhase(meStatusCode: 200, accountsExist: nil) == .authenticated)
        #expect(SessionStore.resolvePhase(meStatusCode: 200, accountsExist: true) == .authenticated)
        #expect(SessionStore.resolvePhase(meStatusCode: 200, accountsExist: false) == .authenticated)
    }

    @Test("me == 404 means multi-user is disabled — no gate")
    func notFoundDisablesGate() {
        #expect(SessionStore.resolvePhase(meStatusCode: 404, accountsExist: nil) == .disabled)
        #expect(SessionStore.resolvePhase(meStatusCode: 404, accountsExist: false) == .disabled)
    }

    @Test("identity probe disables the gate when multi-user is off")
    func singleUserIdentityDisablesGate() {
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: true,
            multiuserEnabled: false
        ) == .disabled)
        #expect(SessionStore.resolvePhase(
            meStatusCode: -1,
            accountsExist: nil,
            multiuserEnabled: false
        ) == .disabled)
    }

    @Test("401 with zero accounts routes to first-run owner setup")
    func unauthenticatedWithNoAccountsShowsOwnerSetup() {
        #expect(SessionStore.resolvePhase(meStatusCode: 401, accountsExist: false) == .needsOwnerSetup)
    }

    @Test("401 with existing accounts routes to login")
    func unauthenticatedWithAccountsShowsLogin() {
        #expect(SessionStore.resolvePhase(meStatusCode: 401, accountsExist: true) == .needsLogin)
    }

    @Test("an inconclusive account probe fails closed to login, never owner setup")
    func inconclusiveProbeFailsClosedToLogin() {
        // nil = probe couldn't determine (e.g. remote engine, no bootstrap). We
        // must NOT assume a fresh install and offer to create an owner.
        #expect(SessionStore.resolvePhase(meStatusCode: 401, accountsExist: nil) == .needsLogin)
        #expect(SessionStore.resolvePhase(meStatusCode: -1, accountsExist: nil) == .needsLogin)
    }

    // MARK: - Identity-resolved owner / first-run bootstrap (#3819)

    @Test("an identity-resolved user proceeds and never shows a create-user wall")
    func identityResolvedUserProceeds() {
        // `GET /api/auth/identity` resolved the credential to a user — on a
        // fresh single-user install that's the auto-bootstrapped local owner
        // (auth_kind == "bootstrap"), even though `/auth/me` 401s. Proceed as
        // that owner regardless of whether a users row was pre-seeded.
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: false,
            multiuserEnabled: true,
            identityUserResolved: true
        ) == .disabled)
        // Existing-owner second launch: still resolves a user, still proceeds —
        // no login wall the local owner has no password for.
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: true,
            multiuserEnabled: true,
            identityUserResolved: true
        ) == .disabled)
    }

    @Test("no identity user with zero accounts still routes to owner setup (remote)")
    func noIdentityUserKeepsRemoteWall() {
        // identityUserResolved defaults false; when the credential resolves to
        // nobody the wall still applies so a remote library never 401/403s.
        #expect(SessionStore.resolvePhase(meStatusCode: 401, accountsExist: false) == .needsOwnerSetup)
        #expect(SessionStore.resolvePhase(meStatusCode: 401, accountsExist: true) == .needsLogin)
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: false,
            multiuserEnabled: true,
            identityUserResolved: false
        ) == .needsOwnerSetup)
    }

    // MARK: - Loopback bootstrap owner is never gated (#3941)

    @Test("the exact payload a live loopback engine returns must not gate")
    func liveLoopbackBootstrapPayloadNeverGates() {
        // Captured verbatim from a running embedded engine with multi-user
        // persisted ON, the app holding the 0600 bootstrap token:
        //
        //   GET /api/auth/me       -> 401
        //   GET /api/auth/identity -> {"multiuser_enabled": true,
        //                              "auth_kind": "bootstrap",
        //                              "user": null,
        //                              "is_owner_access": true}
        //
        // `user` is null — so identityUserResolved is false and #3819's flag
        // cannot fire. Before #3941 this fell through to `.needsLogin` and put
        // a sign-in wall in front of the Mac that owns the engine. The engine
        // had already answered the question: is_owner_access.
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: true,
            multiuserEnabled: true,
            identityUserResolved: false,
            isOwnerAccess: true
        ) == .disabled)
    }

    @Test("owner access ungates whatever the account probe says")
    func ownerAccessOutranksAccountCount() {
        // accountsExist must not change the answer: the bootstrap caller is the
        // owner on an empty install and on a populated one alike. Zero accounts
        // previously meant `.needsOwnerSetup` — asking the owner to create the
        // owner.
        for accountsExist in [true, false, nil] as [Bool?] {
            #expect(SessionStore.resolvePhase(
                meStatusCode: 401,
                accountsExist: accountsExist,
                multiuserEnabled: true,
                isOwnerAccess: true
            ) == .disabled)
        }
    }

    @Test("owner access does not paper over a real remote session expiry")
    func remoteSessionExpiryStillGates() {
        // A remote engine never reports is_owner_access for a session-less
        // caller (bootstrap is loopback-only, auth.py rejects it otherwise), so
        // the wall must still stand when the engine says we are NOT the owner.
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: true,
            multiuserEnabled: true,
            identityUserResolved: false,
            isOwnerAccess: false
        ) == .needsLogin)
    }

    @Test("an unreachable identity probe still fails closed to login")
    func identityProbeFailureFailsClosed() {
        // `identity()` returning nil means we could not ask. isOwnerAccess
        // defaults to false — never assume owner because a probe broke.
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: nil,
            multiuserEnabled: nil
        ) == .needsLogin)
    }

    // MARK: - Failed probes are "unknown", never "signed out" (#4348 class, #4359)

    @Test("a total probe failure keeps the prior phase — failure is not sign-out")
    func totalProbeFailureKeepsPriorPhase() {
        // `refresh()` routes here when the me-probe threw (no HTTP answer) AND
        // the identity probe resolved nothing: the server never SAID anything,
        // so nothing may resolve. Before #4359 this fell into `.needsLogin`
        // and put a full-window sign-in wall in front of the loopback owner
        // whenever a transient transport failure hit mid-refresh.
        for prior in [SessionStore.Phase.disabled, .authenticated, .checking, .needsLogin, .needsOwnerSetup] {
            #expect(SessionStore.phaseAfterUnresolvedProbes(prior: prior) == prior)
        }
    }

    @Test("a failed probe never yields needsLogin from an ungated prior state")
    func failedProbeNeverGatesAnUngatedSession() {
        // The two states that grant library access must survive a probe outage
        // untouched — the #4348 defect class is exactly a failure resolving to
        // "signed out".
        #expect(SessionStore.phaseAfterUnresolvedProbes(prior: .disabled) != .needsLogin)
        #expect(SessionStore.phaseAfterUnresolvedProbes(prior: .authenticated) != .needsLogin)
    }

    @Test("requiresAuthUI is false for checking — an undetermined gate shows no auth chrome")
    func checkingPhaseRequiresNoAuthUI() throws {
        // Structural companion to the sheet gating in ContentView: `.checking`
        // (which includes failed probes after phaseAfterUnresolvedProbes) must
        // never present sign-in chrome. Verified at the source level because
        // SessionStore.phase has a private setter.
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Models/SessionStore.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        #expect(source.contains("var requiresAuthUI: Bool {"))
        #expect(source.contains("phase == .needsLogin || phase == .needsOwnerSetup"))
    }

    @Test("auth error messages never echo secrets and stay category-specific")
    func authErrorMessagesAreSafe() {
        let messages = [
            AuthError.invalidInput.errorDescription,
            AuthError.login(statusCode: 401).errorDescription,
            AuthError.login(statusCode: 429).errorDescription,
            AuthError.createOwner(statusCode: 409).errorDescription
        ]
        for message in messages {
            #expect(message != nil)
            #expect(message?.isEmpty == false)
        }
        // Distinct categories produce distinct guidance.
        #expect(AuthError.login(statusCode: 401).errorDescription != AuthError.login(statusCode: 429).errorDescription)
        #expect(AuthError.createOwner(statusCode: 409).errorDescription != AuthError.login(statusCode: 401).errorDescription)
        // The invite-redeem category also produces safe, specific guidance (#3157).
        #expect(AuthError.redeemInvite(statusCode: 401).errorDescription?.isEmpty == false)
        #expect(AuthError.redeemInvite(statusCode: 401).errorDescription
            != AuthError.redeemInvite(statusCode: 409).errorDescription)
    }

    @Test("owner setup defaults a blank display name to the username")
    func ownerSetupDefaultsDisplayName() {
        #expect(SessionStore.ownerDisplayName("", username: "solo-owner") == "solo-owner")
        #expect(SessionStore.ownerDisplayName("  \n ", username: "solo-owner") == "solo-owner")
    }

    @Test("owner setup preserves an explicit display name")
    func ownerSetupPreservesDisplayName() {
        #expect(SessionStore.ownerDisplayName("  Solo Owner  ", username: "solo-owner") == "Solo Owner")
    }

    // MARK: - Invite link parsing (#3157)

    @Test("a well-formed invite link yields its token")
    func inviteLinkYieldsToken() throws {
        let url = try #require(URL(string: "fichero://invite?token=abc123"))
        #expect(SessionStore.inviteToken(from: url) == "abc123")
    }

    @Test("percent-encoded tokens are decoded")
    func inviteLinkDecodesPercentEncoding() throws {
        let url = try #require(URL(string: "fichero://invite?token=a%2Fb%3Dc"))
        #expect(SessionStore.inviteToken(from: url) == "a/b=c")
    }

    @Test("non-invite links and malformed links yield nil")
    func nonInviteLinksYieldNil() throws {
        let cases = [
            "fichero://pair?token=abc",   // wrong host
            "https://invite?token=abc",   // wrong scheme
            "fichero://invite",           // no token
            "fichero://invite?token="     // empty token
        ]
        for string in cases {
            let url = try #require(URL(string: string))
            #expect(SessionStore.inviteToken(from: url) == nil)
        }
    }
}
