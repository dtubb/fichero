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
}
