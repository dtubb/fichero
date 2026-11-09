import Foundation
import XCTest

@testable import Fichero

/// Step 8.14 (#6434): the popover lists every connection as one row, no sentences.
final class ConnectionPopoverRowsTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 10_000)
    private let awake = PairedMachine(id: "https://mini.tail1.ts.net:8765", name: "Mac mini", libraries: ["/x/Marshall.fichero"])
    private let asleep = PairedMachine(id: "https://studio.local:8765", name: "Studio", libraries: ["/x/Jesuits.fichero"])

    private func rows(inUse: String? = nil) -> [ConnectionRows.Row] {
        ConnectionRows.rows(.init(
            local: .running, machines: [awake, asleep], openHosts: [awake.id],
            lastAnswered: [awake.id: now.addingTimeInterval(-120)], inUse: inUse, now: now))
    }

    /// The spec's acceptance: local engine running, two paired Macs, one asleep.
    func testThreeRowsThisMacOneConnectedOneAsleep() {
        let shown = rows()
        XCTAssertEqual(shown.map(\.name), ["This Mac", "Mac mini", "Studio"])
        XCTAssertEqual(shown.map(\.state), [.running, .connected, .asleep])
        XCTAssertEqual(shown[1].library, "Marshall")
        XCTAssertEqual(shown[1].lastAnswered, "2 min")
        XCTAssertEqual(shown[1].address, "Tailscale")
        XCTAssertEqual(shown[2].address, "LAN")
        XCTAssertEqual(shown[2].problem, "Not answering")
        XCTAssertEqual(shown[2].fix, .reconnect)
        XCTAssertNil(shown[1].problem)
        XCTAssertEqual(ConnectionRows.connectedCount(shown), 2)
    }

    func testUseIsOfferedOnAConnectedHostAndGreyedOnTheOneInUse() {
        XCTAssertTrue(rows()[1].canUse)
        XCTAssertFalse(rows()[2].canUse)
        XCTAssertFalse(rows(inUse: awake.id)[1].canUse)
        XCTAssertTrue(rows().dropFirst().allSatisfy(\.canDisconnect))
    }

    func testTextBudgetNamesFourWordsProblemsEightNoFullStop() {
        XCTAssertEqual(ConnectionRows.shortName("The Big Mac In The Office"), "The Big Mac In")
        for state in [ConnectionRows.State.asleep, .unreachable] {
            let line = try? XCTUnwrap(ConnectionRows.problemLine(state))
            XCTAssertLessThanOrEqual(line?.split(separator: " ").count ?? 99, ConnectionRows.problemWordBudget)
            XCTAssertFalse(line?.hasSuffix(".") ?? true)
        }
    }

    func testAStoppedEngineOffersRestart() {
        let stopped = ConnectionRows.rows(.init(local: .stopped, machines: [], now: now))
        XCTAssertEqual(stopped[0].fix, .restartEngine)
    }
}
