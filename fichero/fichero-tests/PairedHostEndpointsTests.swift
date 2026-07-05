import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// #3098 — paired-host multi-endpoint failover (LAN → tailnet), endpoint-aware
/// trust, never localhost.
final class PairedHostEndpointsTests: XCTestCase {
    private let lan = BackendHost(
        url: URL(string: "https://192.168.1.42:8765")!,
        spkiPin: "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    )
    private let tailnet = BackendHost(
        url: URL(string: "https://studio.tailabc123.ts.net")!
    )
    private let loopback = BackendHost(url: URL(string: "https://127.0.0.1:8765")!)

    // MARK: - Construction & ordering

    func testPreservesPrimaryFirstOrder() {
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        XCTAssertEqual(endpoints?.primary, lan)
        XCTAssertEqual(endpoints?.endpoints, [lan, tailnet])
    }

    func testDropsLoopbackEndpoint() {
        // Hard rule: a remote paired host must never fail over to localhost.
        let endpoints = PairedHostEndpoints(ordered: [lan, loopback, tailnet])
        XCTAssertEqual(endpoints?.endpoints, [lan, tailnet])
        XCTAssertFalse(endpoints?.endpoints.contains(where: { $0.isLocal }) ?? true)
    }

    func testNilWhenOnlyLoopbackSupplied() {
        // No honest remote endpoint → no paired host to model (fail closed, not
        // silently resolve to the local engine).
        XCTAssertNil(PairedHostEndpoints(ordered: [loopback]))
        XCTAssertNil(PairedHostEndpoints(ordered: []))
    }

    func testDeduplicatesByHostKeepingFirst() {
        let lanDuplicate = BackendHost(url: URL(string: "https://192.168.1.42:8765")!)
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet, lanDuplicate])
        XCTAssertEqual(endpoints?.endpoints, [lan, tailnet])
        // The pinned original is kept, not the later pin-less duplicate.
        XCTAssertEqual(endpoints?.primary.spkiPin, lan.spkiPin)
    }

    // MARK: - Endpoint-aware trust travels with the endpoint

    func testEachEndpointCarriesItsOwnTrust() {
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        // LAN endpoint keeps its SPKI pin (self-signed, pinned).
        XCTAssertEqual(endpoints?.endpoints[0].spkiPin, lan.spkiPin)
        XCTAssertEqual(endpoints?.endpoints[0].tokenKind, .remote)
        // Tailnet endpoint has no pin (Tailscale real cert) — never inherits the
        // LAN pin.
        XCTAssertNil(endpoints?.endpoints[1].spkiPin)
        XCTAssertEqual(endpoints?.endpoints[1].tokenKind, .remote)
    }

    // MARK: - Failover walk

    func testNextAfterPrimaryYieldsSecondary() {
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        XCTAssertEqual(endpoints?.next(after: lan), tailnet)
    }

    func testNextAfterLastYieldsNil() {
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        // Nowhere left to go — caller must surface unreachable, never loop back.
        XCTAssertNil(endpoints?.next(after: tailnet))
    }

    func testNextAfterUnknownEndpointYieldsNil() {
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        let stranger = BackendHost(url: URL(string: "https://10.0.0.9:8765")!)
        XCTAssertNil(endpoints?.next(after: stranger))
    }

    // MARK: - Surfaced state (never a silent dead connection)

    func testFailoverReasonNamesBothHosts() {
        let reason = PairedHostEndpoints.failoverReason(from: lan, to: tailnet)
        XCTAssertTrue(reason.contains("192.168.1.42"))
        XCTAssertTrue(reason.contains("studio.tailabc123.ts.net"))
    }

    func testExhaustedReasonNamesLastHostAndNoLocalhost() {
        let reason = PairedHostEndpoints.exhaustedReason(lastTried: tailnet)
        XCTAssertTrue(reason.contains("studio.tailabc123.ts.net"))
        XCTAssertFalse(reason.lowercased().contains("localhost"))
        XCTAssertFalse(reason.contains("127.0.0.1"))
    }
}
