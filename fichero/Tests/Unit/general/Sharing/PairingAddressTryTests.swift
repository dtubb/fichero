@testable import Fichero
import Foundation
import Testing

/// `sharing.client-tries-every-address`, `sharing.ios-link-has-one-address` (Step 2.3): in order, 5 s each, stop at the first answer,
/// and say what happened to each.
struct PairingAddressTryTests {
    private let local = "https://m.local:8765"
    private let tail = "https://m.tail1234.ts.net:8765"
    private let lan = "https://192.0.2.10:8765"

    /// One closure argument, so the attempt can trail; the clock is real (5 s) unless a test asks for an instant one.
    private func tryAddresses(_ addresses: [String], instantClock: Bool = false,
                              _ attempt: @escaping @Sendable (String) async -> PairingFailure?) async -> PairingAddressTry.Outcome {
        await PairingAddressTry.run(
            addresses: addresses,
            sleep: instantClock ? { _ in } : { _ in try? await Task.sleep(nanoseconds: 5_000_000_000) },
            attempt: attempt)
    }

    @Test func addressOneFailsAndTwoAnswersThenTheThirdIsNeverAsked() async {
        let asked = Asked()
        let outcome = await tryAddresses([local, tail, lan]) { url in
            await asked.add(url)
            return url == local ? .nameNotFound : nil
        }
        #expect(outcome.chosen == tail)
        #expect(await asked.urls == [local, tail])
        #expect(outcome.sentence.hasPrefix("Connected through Tailscale (m.tail1234.ts.net)."))
        #expect(outcome.sentence.contains("The m.local address did not answer: this device cannot find that name"))
    }

    @Test func aHangingAddressIsCutAtTheBudgetNotWaitedOn() async {
        // The injected clock returns at once, so the hung attempt loses the race immediately: nothing waits 5 seconds.
        let outcome = await tryAddresses([local, lan], instantClock: true) { url in
            if url == local { try? await Task.sleep(nanoseconds: 60_000_000_000) }
            return nil
        }
        #expect(outcome.attempts.first?.failure == .noAnswer)
        #expect(outcome.chosen == lan)
    }

    @Test func whenNoneAnswersEveryAttemptIsNamedInOneSentence() async {
        let outcome = await tryAddresses([local, tail, lan]) { url in
            url == tail ? .noAnswer : (url == local ? .nameNotFound : .noAnswer)
        }
        #expect(outcome.chosen == nil)
        #expect(outcome.sentence.hasPrefix("Could not reach m.local. Tried "))
        #expect(outcome.sentence.contains("Tailscale (m.tail1234.ts.net): no answer in 5 s: is Tailscale on this device?"))
        #expect(!outcome.sentence.contains("-1001") && !outcome.sentence.lowercased().contains("timed out"))
    }

    @Test func atMostThreeAddressesAreTried() async {
        let asked = Asked()
        let many = (10..<14).map { "https://192.0.2.\($0):8765" }
        _ = await tryAddresses(many) { url in
            await asked.add(url)
            return .noAnswer
        }
        #expect(await asked.urls.count == PairingAddressTry.maxAddresses)
    }

    @Test func aPhoneLinkWithALocalNameFirstPairsOverTheTailnetAddress() async {
        let outcome = await tryAddresses([local, tail]) { url in
            url == local ? .nameNotFound : nil
        }
        #expect(outcome.chosen == tail)
    }
}

private actor Asked {
    private(set) var urls: [String] = []
    func add(_ url: String) { urls.append(url) }
}
