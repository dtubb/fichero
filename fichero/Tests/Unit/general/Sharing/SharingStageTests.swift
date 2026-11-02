@testable import Fichero
import Foundation
import Testing

/// `sharing.setup-asks-sharing`, `sharing.setup-answers-change-later` (Step 4.2): the page's own words and rules.
struct SharingStageTests {
    @Test func eachQuestionHasItsGreyLine() {
        #expect(SharingStageModel.note(forQuestion: SharingStageModel.sharingKey)
                == "Others open it by a link or QR code. Nothing is shared until you say yes.")
        let accounts = SharingStageModel.note(forQuestion: SharingStageModel.accountsKey)
        #expect(accounts?.hasPrefix("Each person signs in with their own name") == true)
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

    @Test func accountsWithoutSharingAndSharingWithoutAccountsEachSaySoAndBothYesSayNothingExtra() {
        let noSharing = SharingStageModel.accountLines(wantsSharing: false, wantsAccounts: true, accountsOn: true)
        #expect(noSharing == [AccountsOnSequence.anyoneElseNote])
        let noAccounts = SharingStageModel.accountLines(wantsSharing: true, wantsAccounts: false, accountsOn: false)
        #expect(noAccounts == [SharingStageModel.linkOpensAsYou])
        #expect(SharingStageModel.accountLines(wantsSharing: true, wantsAccounts: true, accountsOn: true).isEmpty)
        #expect(SharingStageModel.accountLines(wantsSharing: false, wantsAccounts: false, accountsOn: false).isEmpty, "both No: nothing")
    }

    @Test func aYesWhileAccountsAreOffSaysSoAndOffersToTurnThemOn() {
        let lines = SharingStageModel.accountLines(wantsSharing: true, wantsAccounts: true, accountsOn: false)
        #expect(lines == [SharingStageModel.accountsOffNote])
        #expect(SharingStageModel.accountsAction(wantsAccounts: true, accountsOn: false) == .turnOn)
        #expect(SharingStageModel.accountsAction(wantsAccounts: false, accountsOn: true) == .turnOff)
        #expect(SharingStageModel.accountsAction(wantsAccounts: true, accountsOn: true) == nil)
        #expect(SharingStageModel.accountsAction(wantsAccounts: false, accountsOn: false) == nil)
        #expect(SharingStageModel.turnOffAsk == "Everyone returns to being the owner. Turn off?")
    }

    @Test func aMacThatAlreadySharesSaysSoInsteadOfAskingAgain() {
        #expect(SharingStageModel.alreadySharesLine(sharingIsOn: true, wantsSharing: false) == SharingStageModel.alreadyShares)
        #expect(SharingStageModel.alreadySharesLine(sharingIsOn: true, wantsSharing: true) == nil)
        #expect(SharingStageModel.alreadySharesLine(sharingIsOn: false, wantsSharing: false) == nil)
    }
}
