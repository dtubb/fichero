@testable import Fichero
import Testing

/// `sharing.people-pane-off-state` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.4, #5917): with Multi-user off the
/// People pane offers nothing that would end in the engine's 404, and says where the switch is, per platform.
/// Written 2026-10-31, not yet built (no Xcode run on this Mac).
struct PeoplePaneOffStateTests {
    @Test("off: the owner gets no add control and the line; on: the add control and no line")
    func addFollowsTheSwitch() {
        #expect(!PeoplePaneOffState.offersAdd(multiuserOn: false, isOwner: true))
        #expect(PeoplePaneOffState.offersAdd(multiuserOn: true, isOwner: true))
        #expect(!PeoplePaneOffState.offersAdd(multiuserOn: true, isOwner: false), "never for a non-owner")
        #expect(PeoplePaneOffState.words(multiuserOn: true, isOwner: true) == nil)
        #expect(PeoplePaneOffState.words(multiuserOn: false, isOwner: false) == nil, "a non-owner reads the owner-only note, not this")
    }

    @Test("a Mac names the Sharing section and offers the hop; a phone or iPad names the Mac and offers nothing")
    func wordsPerPlatform() throws {
        let mac = try #require(PeoplePaneOffState.words(multiuserOn: false, isOwner: true, platformHasSwitch: true))
        #expect(mac.line.hasPrefix("Multi-user is off.") && mac.line.contains("Sharing"))
        #expect(mac.button == "Open Sharing")
        let phone = try #require(PeoplePaneOffState.words(multiuserOn: false, isOwner: true, platformHasSwitch: false))
        #expect(phone.line.contains("on the Mac that shares this library"))
        #expect(phone.button == nil)
        #if os(macOS)
        #expect(PeoplePaneOffState.platformHasSwitch)
        #else
        #expect(!PeoplePaneOffState.platformHasSwitch)
        #endif
    }

    @Test("the switch's name comes from the one place that names it (#5917)")
    func usesTheSwitchLabel() throws {
        let words = try #require(PeoplePaneOffState.words(multiuserOn: false, isOwner: true, platformHasSwitch: true))
        #expect(words.line.hasPrefix(SharingToggles.label(.multiUser)))
    }
}
