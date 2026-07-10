@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Multi-user auth contracts that back the users/invites UI (#2083, #3157,
/// #3158). Two boundaries the views depend on but that had no direct coverage:
///
/// 1. The `{items,count}` list envelopes (#3158) `UsersStore` reads via
///    `.body.json.items` — a decode test pins the shape so a backend envelope
///    drift is caught at the client schema, not by a blank users list at runtime.
/// 2. `SessionStore`'s pure invite-link parser and phase resolver edge cases
///    (case-insensitive scheme/host, extra query items, non-200/404 statuses).
@Suite("Multi-user auth envelopes & parsing")
struct MultiUserAuthEnvelopeTests {

    // MARK: - {items,count} list envelopes (#3158)

    @Test("a populated user-list envelope decodes to its items")
    func userListEnvelopeDecodesItems() throws {
        let json = """
        {"items":[
          {"id":"u1","username":"ann","display_name":"Ann","is_owner":true,"active":true,"created_at":"2026-07-01T00:00:00Z"}
        ],"count":1}
        """
        let envelope = try JSONDecoder().decode(
            Components.Schemas.UserListResponse.self,
            from: Data(json.utf8)
        )
        #expect(envelope.count == 1)
        #expect(envelope.items.count == 1)
        #expect(envelope.items.first?.id == "u1")
        #expect(envelope.items.first?.username == "ann")
    }

    @Test("an empty user-list envelope decodes to an empty items array")
    func emptyUserListEnvelopeDecodesEmpty() throws {
        let envelope = try JSONDecoder().decode(
            Components.Schemas.UserListResponse.self,
            from: Data(#"{"items":[],"count":0}"#.utf8)
        )
        #expect(envelope.items.isEmpty)
        #expect(envelope.count == envelope.items.count)   // 0, phrased to satisfy empty_count lint
    }

    @Test("a populated invite-list envelope decodes to its items")
    func inviteListEnvelopeDecodesItems() throws {
        let json = """
        {"items":[
          {"id":"i1","username":"newcomer","display_name":"New Comer",
           "created_at":"2026-07-01T00:00:00Z","expires_at":"2026-07-08T00:00:00Z"}
        ],"count":1}
        """
        let envelope = try JSONDecoder().decode(
            Components.Schemas.InviteListResponse.self,
            from: Data(json.utf8)
        )
        #expect(envelope.count == 1)
        #expect(envelope.items.first?.id == "i1")
        #expect(envelope.items.first?.username == "newcomer")
    }

    @Test("an empty invite-list envelope decodes to an empty items array")
    func emptyInviteListEnvelopeDecodesEmpty() throws {
        let envelope = try JSONDecoder().decode(
            Components.Schemas.InviteListResponse.self,
            from: Data(#"{"items":[],"count":0}"#.utf8)
        )
        #expect(envelope.items.isEmpty)
    }

    // MARK: - Invite deep-link parsing edge cases (#3157)

    @Test("scheme and host are matched case-insensitively")
    func inviteLinkSchemeAndHostAreCaseInsensitive() throws {
        // The parser lowercases both scheme and host; an uppercased link still parses.
        let url = try #require(URL(string: "FICHERO://INVITE?token=Tok-123"))
        #expect(SessionStore.inviteToken(from: url) == "Tok-123")
    }

    @Test("the token is found among other query items")
    func inviteLinkFindsTokenAmongOtherQueryItems() throws {
        let url = try #require(URL(string: "fichero://invite?ref=email&token=abc&v=2"))
        #expect(SessionStore.inviteToken(from: url) == "abc")
    }

    // MARK: - Phase resolution: non-200/404 statuses (#2021/#2022)

    @Test("any non-200/404 status routes on account count, never authenticates")
    func nonAuthStatusesRouteOnAccountCount() {
        // 403 / 500 / any other status behave like 401: existing accounts → login,
        // a confirmed-empty install → owner setup, unknown → fail closed to login.
        for status in [403, 429, 500, 503] {
            #expect(SessionStore.resolvePhase(meStatusCode: status, accountsExist: true) == .needsLogin)
            #expect(SessionStore.resolvePhase(meStatusCode: status, accountsExist: false) == .needsOwnerSetup)
            #expect(SessionStore.resolvePhase(meStatusCode: status, accountsExist: nil) == .needsLogin)
        }
    }

    @Test("identity probe wins when single-user bootstrap access is active")
    func singleUserIdentityWinsOverAccountRows() {
        #expect(SessionStore.resolvePhase(
            meStatusCode: 401,
            accountsExist: true,
            multiuserEnabled: false
        ) == .disabled)
    }
}
