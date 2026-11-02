import Foundation

/// The words and rules of Set Up's Sharing and accounts page beyond the engine's two questions (`sharing.setup-asks-sharing`,
/// `sharing.setup-answers-change-later`, Step 4.2). Pure: the page hosts the Settings pane's own controls and reads the
/// engine's real state, so a change in either shows in the other at once.
enum SharingStageModel {
    static let stageID = "sharing"
    static let sharingKey = "sharing_open_to_others"
    static let accountsKey = "accounts_each_person"

    static let sharingNote = "Others open it by a link or QR code. Nothing is shared until you say yes."
    static let settingsFooter = "You can change this any time in Settings › Sharing."
    static let sharingOffNote = "You asked for this library to be open to others, but sharing is off. Turn it on below."

    static let accountsNote = "Each person signs in with their own name, and what they change is recorded under it. "
        + "For anyone else to join, sharing has to be on as well."
    static let linkOpensAsYou = "Anyone you give the link to can open this library as you. "
        + "Turn on accounts to give people their own sign-in."
    static let accountsOffNote = "You asked for each person to have an account, but accounts are off."
    static let turnOffAsk = "Everyone returns to being the owner. Turn off?"
    static let alreadyShares = "This Mac already shares libraries. Share this one too from the project's Share sheet."

    /// The grey line under a question; nil for a question that has none.
    static func note(forQuestion key: String) -> String? {
        switch key {
        case sharingKey: sharingNote
        case accountsKey: accountsNote
        default: nil
        }
    }

    /// The lines under the two answers, given the answers and the Mac's real state (`sharing.setup-asks-accounts`):
    /// Yes to accounts with sharing off says what it means; Yes to sharing with accounts off says whose view a link gives.
    static func accountLines(wantsSharing: Bool, wantsAccounts: Bool, accountsOn: Bool) -> [String] {
        var lines: [String] = []
        if let said = AccountsOnSequence.sharingNote(accountsOn: wantsAccounts, sharingOn: wantsSharing) { lines.append(said) }
        if wantsSharing, !wantsAccounts { lines.append(linkOpensAsYou) }
        if wantsAccounts, !accountsOn { lines.append(accountsOffNote) }
        return lines
    }

    /// A Mac that already shares needs no question again: the page says so and points at the per-project Share sheet
    /// (open question 3: asked once per Mac).
    static func alreadySharesLine(sharingIsOn: Bool, wantsSharing: Bool) -> String? { sharingIsOn && !wantsSharing ? alreadyShares : nil }

    /// What the page offers beside the accounts answer: turn them on (Yes, engine off), turn them off after asking once
    /// (No, engine on), else nothing.
    enum AccountsAction: Equatable { case turnOn, turnOff }
    static func accountsAction(wantsAccounts: Bool, accountsOn: Bool) -> AccountsAction? {
        switch (wantsAccounts, accountsOn) {
        case (true, false): .turnOn
        case (false, true): .turnOff
        default: nil
        }
    }

    /// Saying Yes shows the Settings pane's controls in place; saying No shows none (and starts nothing).
    static func showsSharingControls(wantsSharing: Bool) -> Bool { wantsSharing }

    /// The saved answer and the Mac's engine disagree: said, with where to act (`sharing.setup-answer-is-per-library`).
    static func mismatch(wantsSharing: Bool, sharingIsOn: Bool) -> String? {
        wantsSharing && !sharingIsOn ? sharingOffNote : nil
    }
}
