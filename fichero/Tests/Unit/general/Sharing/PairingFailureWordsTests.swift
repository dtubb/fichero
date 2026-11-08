@testable import Fichero
import Foundation
import Testing

/// `sharing.failure-names-the-step`, `sharing.version-mismatch-says-which-side`, `sharing.token-expired-or-rotated`
/// (Step 2.1): every failure has its one sentence, in words a person can read, and the transport's codes map to a step.
struct PairingFailureWordsTests {
    private let context = PairingFailure.Context(host: "macbook-air-m1", hostVersion: "2026.10.27", thisVersion: "2026.10.28")

    @Test func everyCaseHasASentenceWithNoCodeAndNoJargon() {
        let banned = ["undocumented", "NSURLError", "statusCode", "SSL", "NSError"]
        for failure in PairingFailure.allCases {
            let text = failure.sentence(context)
            #expect(!text.isEmpty, "\(failure)")
            for word in banned { #expect(!text.contains(word), "\(failure): \(word)") }
            #expect(text.range(of: #"-?\b\d{4}\b"#, options: .regularExpression) == nil || failure == .versionMismatch,
                    "\(failure) shows a bare code: \(text)")
        }
    }

    @Test func theStepsRunInTheOrderTheSpecNumbersThem() {
        #expect(PairingFailure.invalidLink.step < PairingFailure.nameNotFound.step)
        #expect(PairingFailure.noAnswer.step < PairingFailure.certificatePin.step)
        #expect(PairingFailure.codeUsedOrExpired.step < PairingFailure.versionMismatch.step)
        #expect(PairingFailure.deviceForgotten.step == 10)
    }

    @Test func everyTransportCodeTheClientCanThrowMapsToACase() {
        #expect(PairingFailure.from(urlErrorCode: -1003, host: "x.local") == .nameNotFound)
        #expect(PairingFailure.from(urlErrorCode: -1003, host: "x.tail1234.ts.net") == .tailnetNameNotFound)
        #expect(PairingFailure.from(urlErrorCode: -1001, host: "x.local") == .noAnswer)
        #expect(PairingFailure.from(urlErrorCode: -1004, host: "x.local") == .refused)
        #expect(PairingFailure.from(urlErrorCode: -1009, host: "x.local") == .offline)
        #expect(PairingFailure.from(urlErrorCode: -1005, host: "x.local") == .noAnswer)
        #expect(PairingFailure.from(urlErrorCode: -1200, host: "x.local") == .certificatePin)
        #expect(PairingFailure.from(urlErrorCode: -1202, host: "x.local") == .certificatePin)
    }

    @Test func anErrorThatIsNotATransportErrorIsNotReportedAsNoAnswer() {
        struct Odd: Error {}
        #expect(LivePairingHost.failure(from: Odd(), host: "x.local") == .unexpected)
        #expect(LivePairingHost.failure(from: RemoteCertificatePinningError.missingSPKIPin, host: "x.local") == .unexpected)
        let transport = NSError(domain: NSURLErrorDomain, code: -1001)
        #expect(LivePairingHost.failure(from: transport, host: "x.local") == .noAnswer)  // a real timeout still is
        #expect(PairingFailure.unexpected.step == PairingFailure.noAnswer.step)
    }

    @Test func aTailnetNumberFailsInItsOwnWords() {
        #expect(PairingFailure.from(urlErrorCode: -1200, host: "100.64.0.1") == .tailnetByNumber)
        #expect(PairingFailure.tailnetByNumber.sentence(context).contains("by name, not by number"))
    }

    @Test func theVersionSentenceNamesBothVersionsAndTheOlderMac() {
        let text = PairingFailure.versionMismatch.sentence(context)
        #expect(text.contains("2026.10.27") && text.contains("2026.10.28"))
        #expect(text.contains("Update macbook-air-m1."))  // the host is the older one
        let newer = PairingFailure.Context(host: "macbook-air-m1", hostVersion: "2026.10.29", thisVersion: "2026.10.28")
        #expect(PairingFailure.versionMismatch.sentence(newer).contains("Update this Mac."))
    }

    @Test func aHostThatForgotThisDeviceSaysSoAndAnswersMapToTheirStep() {
        #expect(PairingFailure.deviceForgotten.sentence(context) == "macbook-air-m1 no longer knows this Mac. Ask for a new link.")
        #expect(PairingFailure.from(status: 401, detail: "invalid or expired pairing code") == .codeUsedOrExpired)
        #expect(PairingFailure.from(status: 401, detail: "person required: x") == .personRequired)
        #expect(PairingFailure.from(status: 401, detail: "missing or invalid Authorization header") == .deviceForgotten)
        #expect(PairingFailure.from(status: 429, detail: "") == .tooManyTries)
    }
}
