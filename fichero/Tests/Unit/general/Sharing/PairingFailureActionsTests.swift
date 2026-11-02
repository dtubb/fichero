@testable import Fichero
import Foundation
import Testing

/// `sharing.ios-says-which-step`, `sharing.ios-tailscale-not-on-the-phone` (Step 5.2): what the phone's sheet offers.
struct PairingFailureActionsTests {
    private let context = PairingFailure.Context(host: "macbook-air-m1", hostVersion: "2026.10.27", thisVersion: "2026.10.28")

    @Test func aTailnetNameThatDoesNotResolveOffersTryAgainOpenTailscaleAndCopyDetails() {
        #expect(PairingFailureActions.actions(for: .tailnetNameNotFound) == [.tryAgain, .openTailscale, .copyDetails])
        #expect(PairingFailureActions.actions(for: .nameNotFound) == [.tryAgain, .copyDetails], "no Tailscale for a .local name")
    }

    @Test func aFailureNoRetryCanMendOffersNoTryAgain() {
        for failure in [PairingFailure.invalidLink, .olderLink, .codeUsedOrExpired, .versionMismatch, .deviceForgotten] {
            #expect(!PairingFailureActions.actions(for: failure).contains(.tryAgain), "\(failure)")
            #expect(PairingFailureActions.actions(for: failure).contains(.copyDetails), "\(failure)")
        }
    }

    @Test func everyCaseOffersCopyDetailsAndOnlyTheTailnetNameOffersTailscale() {
        for failure in PairingFailure.allCases {
            let actions = PairingFailureActions.actions(for: failure)
            #expect(actions.contains(.copyDetails), "\(failure)")
            #expect(actions.contains(.openTailscale) == (failure == .tailnetNameNotFound), "\(failure)")
        }
        #expect(PairingFailureActions.actions(for: nil) == [.copyDetails], "an error that is not a pairing step")
    }

    @Test func theDetailsNameTheStepTheSentenceAndBothVersionsAndNoSecret() {
        let text = PairingFailureActions.details(.noAnswer, context: context)
        #expect(text.contains("Step 3:") && text.contains(PairingFailure.noAnswer.sentence(context)))
        #expect(text.contains("2026.10.27") && text.contains("2026.10.28") && text.contains("macbook-air-m1"))
        for word in ["token", "code ", "pin "] { #expect(!text.lowercased().contains(word), word) }
    }

    @Test func theButtonsHaveTheSpecsWords() {
        #expect(PairingFailureActions.title(.tryAgain) == "Try again")
        #expect(PairingFailureActions.title(.copyDetails) == "Copy details")
        #expect(PairingFailureActions.title(.openTailscale) == "Open Tailscale")
    }
}
