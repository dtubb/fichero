import Foundation

/// What the People pane shows while Multi-user is off (`sharing.people-pane-off-state`, #5917): no `+`, no Create Account,
/// no Invite (each would end in the engine's 404 `multi-user auth is disabled`), one line that names the switch where it is,
/// and, on the platform that has the switch, a button that goes there. Phones and iPads have no switch
/// (`SharingSettingsView.availableSections` is People only there), so their line names the Mac instead.
enum PeoplePaneOffState: Equatable {
    struct Words: Equatable {
        let line: String
        /// The button that hops to the Sharing section; nil where there is no switch to hop to.
        let button: String?
    }

    /// Whether this platform holds the Multi-user switch (Settings › Sharing › Devices › Advanced on a Mac).
    static var platformHasSwitch: Bool {
        #if os(macOS)
        return true
        #else
        return false
        #endif
    }

    /// The owner may add people only while Multi-user is on; a non-owner never may.
    static func offersAdd(multiuserOn: Bool, isOwner: Bool) -> Bool {
        isOwner && multiuserOn
    }

    /// The line and button for the owner while Multi-user is off; nil while it is on or for a non-owner (who reads the
    /// owner-only note instead).
    static func words(multiuserOn: Bool, isOwner: Bool, platformHasSwitch: Bool = platformHasSwitch) -> Words? {
        guard isOwner, !multiuserOn else { return nil }
        let name = SharingToggles.label(.multiUser)
        if platformHasSwitch {
            return Words(line: AccountsOnSequence.offSentence, button: AccountsOnSequence.buttonTitle)
        }
        return Words(line: "\(name) is off. Turn it on in Sharing on the Mac that shares this library.", button: nil)
    }
}
