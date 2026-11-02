@testable import Fichero
import Foundation
import Testing

/// `sharing.address-choice` (Step 3.1 residue): the sheet's lines for the engine's address list.
struct HostAddressRecordTests {
    @Test func aWorkingAddressShowsItsLabelAndUrlAndADeadOneSaysWhy() {
        let working = HostAddressRecord(url: "https://m.tail1234.ts.net:8765", listening: true, label: "Tailscale", reason: nil)
        let dead = HostAddressRecord(url: "https://192.0.2.10:8765", listening: false, label: "Wi-Fi", reason: "the port is held")
        #expect(working.line == "Tailscale: https://m.tail1234.ts.net:8765")
        #expect(dead.line == "Wi-Fi can't be used: the port is held")
        #expect(HostAddressRecord.lines([working, dead]).count == 2)
    }

    @Test func noLabelOrReasonStillReadsAsAFullLine() {
        #expect(HostAddressRecord(url: "https://a:1", listening: true, label: nil, reason: nil).line == "https://a:1")
        #expect(HostAddressRecord(url: "https://a:1", listening: false, label: nil, reason: nil).line
            == "https://a:1 can't be used: not available")
    }
}
