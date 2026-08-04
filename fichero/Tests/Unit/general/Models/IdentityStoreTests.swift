@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// F5: IdentityStore decodes `GET /api/auth/identity` and exposes who-am-I
/// correctly across the three auth postures the user will hit — bootstrap-owner
/// (single-user loopback), a signed-in account user, and unauthenticated.
@MainActor
struct IdentityStoreTests {
    private func makeStore() -> IdentityStore {
        IdentityStore(client: FicheroClient())
    }

    private func identity(
        multiuser: Bool,
        authKind: String,
        user: Components.Schemas.AuthIdentityUser?,
        isOwnerAccess: Bool
    ) -> Components.Schemas.AuthIdentityResponse {
        .init(
            multiuserEnabled: multiuser,
            authKind: authKind,
            user: user,
            isOwnerAccess: isOwnerAccess
        )
    }

    // MARK: - Posture 1: bootstrap owner (single-user loopback)

    @Test func bootstrapOwnerIsAuthenticatedOwnerWithNoDisplayName() {
        let store = makeStore()
        store.setIdentityForTesting(identity(
            multiuser: false, authKind: "bootstrap", user: nil, isOwnerAccess: true
        ))
        // No user resolves, but multi-user is off — the bootstrap token is always
        // owner-capable, so this IS authenticated (not a sign-in prompt).
        #expect(store.isAuthenticated)
        #expect(store.isOwnerAccess)
        #expect(!store.multiuserEnabled)
        #expect(store.displayName == nil)
        #expect(store.authKind == "bootstrap")
    }

    // MARK: - Posture 2: signed-in account user

    @Test func accountUserIsAuthenticatedWithDisplayName() {
        let store = makeStore()
        let user = Components.Schemas.AuthIdentityUser(
            id: "u1", username: "testowner", displayName: "Test Owner", isOwner: false
        )
        store.setIdentityForTesting(identity(
            multiuser: true, authKind: "session", user: user, isOwnerAccess: false
        ))
        #expect(store.isAuthenticated)          // a user resolved
        #expect(!store.isOwnerAccess)
        #expect(store.multiuserEnabled)
        #expect(store.displayName == "Test Owner")
        #expect(store.user?.username == "testowner")
    }

    // MARK: - Posture 3: unauthenticated (multi-user on, no session)

    @Test func unauthenticatedIsNotAuthenticated() {
        let store = makeStore()
        store.setIdentityForTesting(identity(
            multiuser: true, authKind: "none", user: nil, isOwnerAccess: false
        ))
        // Multi-user on AND no user resolved → must sign in.
        #expect(!store.isAuthenticated)
        #expect(!store.isOwnerAccess)
    }

    // MARK: - Fail-closed default

    @Test func nilIdentityFailsClosed() {
        let store = makeStore()
        // Never probed / probe failed → treated as NOT authenticated.
        #expect(!store.isAuthenticated)
        #expect(!store.isOwnerAccess)
        #expect(!store.multiuserEnabled)
        #expect(store.displayName == nil)
    }

    // MARK: - Wire contract: the real JSON decodes with snake_case mapping

    @Test func decodesBootstrapOwnerJSON() throws {
        let json = Data(#"{"multiuser_enabled": false, "auth_kind": "bootstrap", "is_owner_access": true}"#.utf8)
        let decoded = try JSONDecoder().decode(Components.Schemas.AuthIdentityResponse.self, from: json)
        #expect(decoded.multiuserEnabled == false)
        #expect(decoded.authKind == "bootstrap")
        #expect(decoded.isOwnerAccess == true)
        #expect(decoded.user == nil)
    }

    @Test func decodesAccountUserJSON() throws {
        let json = Data("""
        {"multiuser_enabled": true, "auth_kind": "session", "is_owner_access": false,
         "user": {"id": "u1", "username": "testowner", "display_name": "Test Owner", "is_owner": false}}
        """.utf8)
        let decoded = try JSONDecoder().decode(Components.Schemas.AuthIdentityResponse.self, from: json)
        #expect(decoded.user?.displayName == "Test Owner")
        #expect(decoded.user?.isOwner == false)
    }

    @Test func nonOwnerUsersSettingsShowsAccountDetailsInsteadOfEmptyState() {
        let presentation = UsersSettingsPresentation.resolve(.init(
            isLoading: false,
            loadError: nil,
            usersEmpty: true,
            hasCurrentUser: true,
            hasAuthzSnapshot: true,
            listAccessDenied: true,
            isOwnerAccess: false
        ))
        #expect(presentation == .accountDetails)
    }

    @Test func ownerStillGetsEmptyStateWhenNoAccountDataExists() {
        let presentation = UsersSettingsPresentation.resolve(.init(
            isLoading: false,
            loadError: nil,
            usersEmpty: true,
            hasCurrentUser: false,
            hasAuthzSnapshot: false,
            listAccessDenied: false,
            isOwnerAccess: true
        ))
        #expect(presentation == .empty)
    }
}
