@testable import Fichero
import Foundation
import Testing

/// `sharing.alerts.one-alert-per-failure` and `sharing.alerts.no-bottom-strip` (Step 8.8, #6361): every pairing or sharing
/// failure is one alert with the table's title, the step's sentence, its fix where the view can do it, Copy Details and OK;
/// no raw error text reaches the message.
@MainActor
struct SharingFailureAlertTests {
    private let context = PairingFailure.Context(host: "Studio")

    private func alert(_ failure: PairingFailure, offers: Set<SharingFailurePrompt.Fix> = Set(SharingFailurePrompt.Fix.allCases))
        -> FailureAlertPrompt {
        SharingFailurePrompt.make(failure, context: context, offers: offers, perform: { _ in }, copy: { _ in })
    }

    @Test func everyStepHasATitleAndItsSentence() {
        for failure in PairingFailure.allCases {
            let shown = alert(failure)
            #expect(!shown.title.isEmpty, "\(failure)")
            #expect(shown.message == failure.sentence(context), "\(failure)")
            #expect(shown.dismissLabel == "OK")
            #expect(shown.fixes.last?.label == "Copy Details", "\(failure)")
        }
    }

    @Test func theFixButtonsAreTheTables() {
        #expect(alert(.invalidLink).fixes.map(\.label) == ["Paste Link Again", "Copy Details"])
        #expect(alert(.tailnetNameNotFound).fixes.map(\.label) == ["Open Tailscale", "Copy Details"])
        #expect(alert(.refused).fixes.map(\.label) == ["Try Again", "Copy Details"])
        #expect(alert(.personRequired).fixes.map(\.label) == ["Sign In…", "Copy Details"])
        #expect(alert(.versionMismatch).fixes.map(\.label) == ["Check for Updates…", "Copy Details"])
        #expect(alert(.hostSharesNothing).fixes.map(\.label) == ["Copy Details"])
        #expect(SharingFailurePrompt.title(.hostSharesNothing, context) == "Studio hasn't shared any project yet")
    }

    @Test func aFixTheViewCannotDoIsNotOffered() {
        #expect(alert(.versionMismatch, offers: SharingFailurePrompt.phoneOffers).fixes.map(\.label) == ["Copy Details"])
    }

    @Test func copyDetailsCopiesTheStepNotTheMessageAlone() {
        var copied = ""
        let shown = SharingFailurePrompt.make(.refused, context: context, offers: [], perform: { _ in }, copy: { copied = $0 })
        shown.fixes.last?.action()
        #expect(copied.contains("Step 3"))
    }

    @Test func aRefusedConnectionIsTheRefusedStep() {
        let error = URLError(.cannotConnectToHost)
        let shown = SharingFailurePrompt.make(pairing: error, host: "studio.local", offers: [.tryAgain], perform: { _ in }, copy: { _ in })
        #expect(shown.title == "studio.local isn't listening")
    }

    @Test func aClientErrorsTextNeverReachesTheMessage() {
        struct ClientNoise: LocalizedError {
            var errorDescription: String? { "Client encountered an error invoking the operation list_devices_api_pair_devices_get" }
        }
        let pairing = SharingFailurePrompt.make(pairing: ClientNoise(), host: "Studio", offers: [], perform: { _ in }, copy: { _ in })
        let sharing = SharingFailurePrompt.make(sharing: ClientNoise(), title: "Couldn't list the paired devices", offers: [],
                                                perform: { _ in }, copy: { _ in })
        #expect(!pairing.message.contains("Client encountered"))
        #expect(!sharing.message.contains("Client encountered"))
    }

    @Test func theEngineNotListeningOffersTurnSharingOffAndOn() {
        var did: SharingFailurePrompt.Fix?
        let refused = NSError(domain: "Client", code: 0, userInfo: [NSUnderlyingErrorKey: URLError(.cannotConnectToHost) as NSError])
        let shown = SharingFailurePrompt.make(sharing: refused, title: "Couldn't turn Sharing on", offers: [.turnSharingOffAndOn],
                                              perform: { did = $0 }, copy: { _ in })
        #expect(shown.message.contains("isn't accepting connections on the sharing port"))
        #expect(shown.fixes.first?.label == "Turn Sharing Off and On")
        shown.fixes.first?.action()
        #expect(did == .turnSharingOffAndOn)
    }

    @Test func aForbiddenShareSaysTheOwnerMustShare() {
        let shown = SharingFailurePrompt.make(sharing: APIError.httpError(statusCode: 403, message: "forbidden"), title: "Couldn't share",
                                              offers: [], perform: { _ in }, copy: { _ in })
        #expect(shown.message.contains("Only this Mac's owner can share"))
    }

    @Test func theEnginesOwnWordsAreShown() {
        let shown = SharingFailurePrompt.make(sharing: APIError.httpError(statusCode: 409, message: "That person already has the project."),
                                              title: "Couldn't share the folder", offers: [], perform: { _ in }, copy: { _ in })
        #expect(shown.message == "That person already has the project.")
    }
}
