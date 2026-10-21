@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `sharing.invite.revoke`: the owner's pending invitations, listed and revoked in place.
@MainActor
struct PairInvitesStoreTests {
    private func invite(_ id: String, role: String? = "editor") -> PairInvitesStore.Invite {
        .init(id: id, person: "ana", newPerson: false, role: role, mintedBy: "owner")
    }

    private struct Refused: LocalizedError {
        var errorDescription: String? { "no such invitation" }
    }

    @Test func loadListsTheEnginesInvitations() async {
        let store = PairInvitesStore(list: { [invite("a"), invite("b")] }, revoke: { _ in })
        await store.load()
        #expect(store.invites.map(\.id) == ["a", "b"])
        #expect(store.errorMessage == nil)
    }

    @Test func revokeRemovesThatRowOnlyAndAskedTheEngineForIt() async {
        var revoked: [String] = []
        let store = PairInvitesStore(list: { [invite("a"), invite("b")] }, revoke: { revoked.append($0) })
        await store.load()
        await store.revoke(invite("a"))
        #expect(revoked == ["a"] && store.invites.map(\.id) == ["b"])
    }

    @Test func aRefusedRevokeKeepsTheRowAndSaysWhy() async {
        let store = PairInvitesStore(list: { [invite("a")] }, revoke: { _ in throw Refused() })
        await store.load()
        await store.revoke(invite("a"))
        #expect(store.invites.map(\.id) == ["a"] && store.errorMessage == "no such invitation")
    }

    @Test func aRowSaysWhatItGivesAndWhenItEnds() {
        let now = Date(timeIntervalSince1970: 1_700_000_000)
        let soon = PendingInviteText.detail(role: "editor", expiresAt: now.addingTimeInterval(600), now: now)
        #expect(soon == "Gives editor · Expires in 10 min")
        #expect(PendingInviteText.detail(role: nil, expiresAt: nil, now: now) == "Keeps the role they have · Never expires")
    }
}
