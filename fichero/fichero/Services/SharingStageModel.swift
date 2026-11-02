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

    /// The grey line under a question; nil for a question that has none.
    static func note(forQuestion key: String) -> String? { key == sharingKey ? sharingNote : nil }

    /// Saying Yes shows the Settings pane's controls in place; saying No shows none (and starts nothing).
    static func showsSharingControls(wantsSharing: Bool) -> Bool { wantsSharing }

    /// The saved answer and the Mac's engine disagree: said, with where to act (`sharing.setup-answer-is-per-library`).
    static func mismatch(wantsSharing: Bool, sharingIsOn: Bool) -> String? {
        wantsSharing && !sharingIsOn ? sharingOffNote : nil
    }
}
