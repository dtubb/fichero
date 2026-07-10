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
