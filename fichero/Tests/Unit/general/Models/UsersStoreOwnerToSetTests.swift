//
//  UsersStoreOwnerToSetTests.swift
//  FicheroTests
//
//  multiuser.turning-on-needs-an-owner-password (#5908): with Multi-user off the people list is empty, so the owner whose
//  password is chosen comes from identity. See docs/contributor_manual/specs/transport/multiuser-always-on.md.
//

@testable import Fichero
import Testing

struct UsersStoreOwnerToSetTests {
    @Test("with Multi-user off and no people listed, identity's owner is the one whose password is set")
    func identityOwnerWhenNothingIsListed() {
        #expect(UsersStore.ownerToSet(signedIn: nil, listed: nil, identity: "owner-1") == "owner-1")
    }

    @Test("the signed-in person, then the listed owner, come before identity's owner")
    func signedInThenListedFirst() {
        #expect(UsersStore.ownerToSet(signedIn: "me", listed: "owner-1", identity: "owner-2") == "me")
        #expect(UsersStore.ownerToSet(signedIn: nil, listed: "owner-1", identity: "owner-2") == "owner-1")
    }

    @Test("no owner known anywhere sets nothing")
    func nobodyKnown() {
        #expect(UsersStore.ownerToSet(signedIn: nil, listed: nil, identity: nil) == nil)
    }
}
