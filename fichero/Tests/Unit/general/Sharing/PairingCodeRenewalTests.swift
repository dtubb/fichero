//
//  PairingCodeRenewalTests.swift
//  FicheroTests
//
//  sharing.pairing-code-renews-at-expiry (#5915): when the Sharing card mints a fresh code.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct PairingCodeRenewalTests {
    private let now = Date(timeIntervalSince1970: 1_000_000)

    @Test func waitsUntilTheCodeExpires() {
        #expect(PairingCodeRenewal.wait(until: now.addingTimeInterval(600), now: now) == .seconds(600))
    }

    @Test func aCodeAlreadyPastItsExpiryStillWaitsTheShortestWait() {
        #expect(PairingCodeRenewal.wait(until: now.addingTimeInterval(-30), now: now) == .seconds(5))
    }

    @Test func aCodeAboutToExpireWaitsNoLessThanTheShortestWait() {
        #expect(PairingCodeRenewal.wait(until: now.addingTimeInterval(1), now: now) == .seconds(5))
    }

    // The expiry path itself (review 597): the renewal returns the fresh code, reports a failure, and is never
    // mistaken for a failure when it is cancelled.
    private let fresh = PairingCodeRecord(code: "NEW-CODE", expiresAt: Date(timeIntervalSince1970: 2_000_000))

    @Test func renewingReturnsTheFreshCode() async {
        let outcome = await PairingCodeRenewal.renew(mint: { fresh })
        guard case .fresh(let code) = outcome else { Issue.record("expected a fresh code"); return }
        #expect(code.code == "NEW-CODE")
    }

    @Test func aFailedMintIsReportedInWords() async {
        struct Down: LocalizedError { var errorDescription: String? { "The engine is not responding." } }
        let outcome = await PairingCodeRenewal.renew(mint: { throw Down() })
        guard case .failed(let message) = outcome else { Issue.record("expected a failure"); return }
        #expect(message == "The engine is not responding.")
    }

    @Test func aCancelledRenewalIsNotAFailure() async {
        let task = Task { await PairingCodeRenewal.renew(mint: { try await Task.sleep(for: .seconds(60)); return fresh }) }
        task.cancel()
        guard case .cancelled = await task.value else { Issue.record("expected cancelled"); return }
    }

    @Test func eachRenewalMintsExactlyOneCode() async {
        var minted = 0
        _ = await PairingCodeRenewal.renew(mint: { minted += 1; return fresh })
        #expect(minted == 1)
    }

    @Test func aCodeMintedAfterTheCardWentAwayIsDropped() async {
        let task = Task {
            await PairingCodeRenewal.renew(mint: {
                try? await Task.sleep(for: .milliseconds(50))  // the card goes away while the mint is in flight
                return fresh
            })
        }
        task.cancel()
        guard case .cancelled = await task.value else { Issue.record("a late code must not be applied"); return }
    }
}
