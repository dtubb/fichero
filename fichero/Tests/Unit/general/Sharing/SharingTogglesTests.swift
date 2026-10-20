//
//  SharingTogglesTests.swift
//  FicheroTests
//
//  RED on purpose (test-first, sharing.two-toggles-wording, #3284/#5049): Settings › Sharing has
//  exactly two switches, Sharing and Multi-user, with the ruled captions, and nothing else is asked.
//  `SharingToggles` is the pure description both switches render from; it does not exist yet, so this
//  file does not compile until #3284 builds it (and moves the Multi-user switch out of Engine settings).
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct SharingTogglesTests {

    @Test func theSharingSwitchSaysWhatItShares() {
        let toggle = SharingToggles.all.first { $0.id == .sharing }
        #expect(toggle?.label == "Sharing")
        #expect(toggle?.caption == "Share Fichero on this Mac with other devices, the fichero command-line tool, and MCP clients.")
    }

    @Test func theMultiUserSwitchSaysWhoItIsFor() {
        let toggle = SharingToggles.all.first { $0.id == .multiUser }
        #expect(toggle?.label == "Multi-user")
        #expect(toggle?.caption == "Give other people their own accounts on this Mac's libraries.")
    }

    @Test func thereAreExactlyTwoSwitchesAndNoThird() {
        #expect(SharingToggles.all.map(\.id) == [.sharing, .multiUser])
    }

    // sharing.people-tab-names-the-multiuser-switch (#5917)
    @Test func theMultiUserOffHintNamesTheSwitchWhereItIs() {
        let hint = SharingToggles.multiUserOffHint
        #expect(hint.contains(SharingToggles.location))
        #expect(hint.contains(SharingToggles.label(.multiUser)))
        #expect(!hint.contains("Engine"))
    }

    @Test func theHintPromisesNoRestart() {
        #expect(!SharingToggles.multiUserOffHint.localizedCaseInsensitiveContains("restart"))
    }

    @Test func aLabelIsFoundByItsIdNotItsPlace() {
        #expect(SharingToggles.label(.sharing) == "Sharing")
        #expect(SharingToggles.label(.multiUser) == "Multi-user")
    }
}
