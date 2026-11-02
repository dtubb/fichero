@testable import Fichero
import Foundation
import Testing

/// `sharing.setup-asks-sharing`, `sharing.setup-answers-change-later` (Step 4.2): the page's own words and rules.
struct SharingStageTests {
    @Test func theSharingQuestionHasItsGreyLineAndTheAccountsQuestionNone() {
        #expect(SharingStageModel.note(forQuestion: SharingStageModel.sharingKey)
                == "Others open it by a link or QR code. Nothing is shared until you say yes.")
        #expect(SharingStageModel.note(forQuestion: SharingStageModel.accountsKey) == nil)
        #expect(SharingStageModel.note(forQuestion: "layout") == nil)
    }

    @Test func noShowsNoControlsAndStartsNothing() {
        #expect(!SharingStageModel.showsSharingControls(wantsSharing: false))
        #expect(SharingStageModel.showsSharingControls(wantsSharing: true))
        #expect(SharingStageModel.mismatch(wantsSharing: false, sharingIsOn: false) == nil)
    }

    @Test func aYesWhileTheEngineIsOffSaysSoAndAnAgreeingEngineSaysNothing() {
        let said = SharingStageModel.mismatch(wantsSharing: true, sharingIsOn: false)
        #expect(said?.hasPrefix("You asked for this library to be open to others, but sharing is off.") == true)
        #expect(SharingStageModel.mismatch(wantsSharing: true, sharingIsOn: true) == nil)
        #expect(SharingStageModel.settingsFooter == "You can change this any time in Settings › Sharing.")
    }
}
