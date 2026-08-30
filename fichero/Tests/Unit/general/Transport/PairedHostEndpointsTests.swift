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

    // MARK: - Failover candidates (order-independent of current position)

    func testFailoverCandidatesExcludeCurrentInPriorityOrder() {
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        // On the LAN endpoint → only the tailnet endpoint remains to try.
        XCTAssertEqual(endpoints?.failoverCandidates(excluding: lan), [tailnet])
    }

    func testFailoverCandidatesCanWalkBackToHigherPriorityEndpoint() {
        // Client paired over the stable tailnet URL but LAN ranks ahead: dropping
        // tailnet must still offer the faster LAN endpoint. `next(after:)` alone
        // (forward-only) would miss it; `failoverCandidates` does not.
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        XCTAssertEqual(endpoints?.failoverCandidates(excluding: tailnet), [lan])
        XCTAssertNil(endpoints?.next(after: tailnet)) // contrast: forward walk is empty
    }

    func testFailoverCandidatesMatchCurrentByNormalizedHost() {
        // A trailing-slash variant of the current endpoint still excludes it.
        let endpoints = PairedHostEndpoints(ordered: [lan, tailnet])
        let lanSlash = BackendHost(url: URL(string: "https://192.168.1.42:8765/")!)
        XCTAssertEqual(endpoints?.failoverCandidates(excluding: lanSlash), [tailnet])
    }

    // MARK: - Persisted endpoint store

    private let storeKey = "fichero.paired.endpoints"

    override func setUp() {
        super.setUp()
        EngineConfig.defaults.removeObject(forKey: storeKey)
    }

    override func tearDown() {
        EngineConfig.defaults.removeObject(forKey: storeKey)
        super.tearDown()
    }

    func testStoreOrdersLANBeforeTailnetRegardlessOfInsertion() {
        // Record tailnet first, then LAN — priority sort must put LAN first.
        PairedHostEndpointStore.record(tailnet.url)
        PairedHostEndpointStore.record(lan.url)
        let hosts = PairedHostEndpointStore.endpoints()
        XCTAssertEqual(hosts.map(\.url.host), ["192.168.1.42", "studio.tailabc123.ts.net"])
    }

    func testStoreDeduplicatesByURL() {
        PairedHostEndpointStore.record(lan.url)
        PairedHostEndpointStore.record(lan.url)
        XCTAssertEqual(PairedHostEndpointStore.endpoints().count, 1)
    }

    func testStoreRefusesLoopback() {
        // A paired host must never resolve to the local engine.
        PairedHostEndpointStore.record(loopback.url)
        XCTAssertTrue(PairedHostEndpointStore.endpoints().isEmpty)
    }

    func testStoreClearForgetsEverything() {
        PairedHostEndpointStore.record(lan.url)
        PairedHostEndpointStore.clear()
        XCTAssertTrue(PairedHostEndpointStore.endpoints().isEmpty)
    }

    // MARK: - Endpoint-correct trust (pin-store seam)

    func testEachEndpointGetsItsOwnPinFromTheStore() {
        // A paired host reachable at both its LAN and tailnet URL: the LAN one is
        // self-signed and SPKI-pinned, the tailnet one has a real cert (no pin).
        // `endpoints(pinFor:)` must attach each URL's OWN pin — never share the
        // LAN pin onto the tailnet endpoint (that would defeat pinning).
        PairedHostEndpointStore.record(lan.url)
        PairedHostEndpointStore.record(tailnet.url)

        let pins = [lan.url.absoluteString: "sha256/LAN-PIN="]
        let hosts = PairedHostEndpointStore.endpoints(pinFor: { pins[$0] })

        XCTAssertEqual(hosts.map(\.url.host), ["192.168.1.42", "studio.tailabc123.ts.net"])
        XCTAssertEqual(hosts[0].spkiPin, "sha256/LAN-PIN=")
        XCTAssertNil(hosts[1].spkiPin) // tailnet real cert — pin never inherited
    }

    func testPinLookupIsKeyedByEndpointURLNotHost() {
        // The pin is resolved by the full URL string the store persisted, so the
        // right trust travels with the exact endpoint the reconnect loop dials.
        PairedHostEndpointStore.record(lan.url)

        var requestedKeys: [String] = []
        _ = PairedHostEndpointStore.endpoints(pinFor: { key in
            requestedKeys.append(key)
            return nil
        })

        XCTAssertEqual(requestedKeys, [lan.url.absoluteString])
    }

    func testAbsentPinYieldsNilTrustNotAFallback() {
        // No pin recorded for the endpoint → nil, never a substituted/other pin.
        PairedHostEndpointStore.record(lan.url)
        let hosts = PairedHostEndpointStore.endpoints(pinFor: { _ in nil })
        XCTAssertEqual(hosts.count, 1)
        XCTAssertNil(hosts[0].spkiPin)
    }
}
