import XCTest
import Foundation
import HTTPTypes
import OpenAPIRuntime
import OpenAPIURLSession
import OpenAPIAsyncHTTPClient
import AsyncHTTPClient
@testable import FicheroAPIClient

/// #4349 — connection-pool segmentation, ceiling, and the near-ceiling tripwire.
///
/// The bug: long-lived SSE subscriptions and short request/response calls drew
/// from ONE `HTTPClient` connection pool whose per-host soft limit was
/// AsyncHTTPClient's inherited default of 8. Stream count grows with the number
/// of open libraries, so past a handful of libraries the streams pinned every
/// connection and ordinary request traffic queued until it timed out.
///
/// Everything here runs headless under plain `swift test` — no socket, no
/// engine. The live-socket acceptance case (4 real SSE subscriptions against a
/// running engine) lives in `TransportRoutingMatrixTests`, gated on
/// `FICHERO_TEST_UDS_PATH` like the rest of the live matrix.
final class ConnectionPoolSegmentationTests: XCTestCase {

    // MARK: - Sizing (pure logic)

    /// The ceilings must be *chosen*, not inherited. 8 is AsyncHTTPClient's
    /// remote-HTTP politeness default; a local AF_UNIX socket to our own
    /// single-tenant engine has none of the reasons behind it.
    func testCeilingsAreWellAboveTheInheritedDefaultOfEight() {
        XCTAssertGreaterThan(
            LocalTransportPool.requestConnectionCeiling, 8,
            "the request pool must not sit on AsyncHTTPClient's inherited default of 8"
        )
        XCTAssertGreaterThan(
            LocalTransportPool.streamConnectionCeiling, 8,
            "the stream pool must not sit on AsyncHTTPClient's inherited default of 8"
        )
        // And bounded: the ceiling is a leak detector. Unbounded growth would
        // hide a connection leak until file-descriptor exhaustion.
        XCTAssertLessThanOrEqual(LocalTransportPool.requestConnectionCeiling, 256)
        XCTAssertLessThanOrEqual(LocalTransportPool.streamConnectionCeiling, 256)
    }

    /// The configured `HTTPClient` must actually carry the chosen soft limit —
    /// building the configuration and forgetting to apply it is the silent way
    /// to ship the default.
    func testLocalConfigurationAppliesTheChosenSoftLimit() {
        let configuration = LocalTransportPool.configuration(softLimit: 37)
        XCTAssertEqual(configuration.connectionPool.concurrentHTTP1ConnectionsPerHostSoftLimit, 37)
        XCTAssertEqual(configuration.connectionPool.idleTimeout, LocalTransportPool.idleTimeout)
        XCTAssertNil(
            configuration.timeout.read,
            "no read timeout: a quiet SSE subscription is healthy, not stalled"
        )
    }

    func testURLSessionConfigurationAppliesThePerHostCap() {
        let configuration = LocalTransportPool.urlSessionConfiguration(maximumConnectionsPerHost: 21)
        XCTAssertEqual(configuration.httpMaximumConnectionsPerHost, 21)
    }

    // MARK: - Near-ceiling threshold (pure logic)

    func testNearCeilingThresholdRoundsUpAndStaysInsideTheCeiling() {
        XCTAssertEqual(LocalTransportPool.nearCeilingThreshold(ceiling: 64), 48)   // 0.75 * 64
        XCTAssertEqual(LocalTransportPool.nearCeilingThreshold(ceiling: 32), 24)
        XCTAssertEqual(LocalTransportPool.nearCeilingThreshold(ceiling: 10), 8)    // 7.5 -> 8
        XCTAssertEqual(LocalTransportPool.nearCeilingThreshold(ceiling: 1), 1)
    }

    /// A nonsense ceiling must never silently disable the tripwire.
    func testNearCeilingThresholdIsClampedForDegenerateCeilings() {
        XCTAssertEqual(LocalTransportPool.nearCeilingThreshold(ceiling: 0), 1)
        XCTAssertEqual(LocalTransportPool.nearCeilingThreshold(ceiling: -5), 1)
    }

    func testIsNearCeilingFiresAtTheThresholdNotBefore() {
        XCTAssertFalse(LocalTransportPool.isNearCeiling(inUse: 47, ceiling: 64))
        XCTAssertTrue(LocalTransportPool.isNearCeiling(inUse: 48, ceiling: 64))
        XCTAssertTrue(LocalTransportPool.isNearCeiling(inUse: 64, ceiling: 64))
        XCTAssertFalse(LocalTransportPool.isNearCeiling(inUse: 0, ceiling: 64))
    }

    // MARK: - Pressure accounting (pure logic)

    func testPressureCountsInUseAndPeak() {
        let pressure = ConnectionPoolPressure(label: "test", ceiling: 8)
        pressure.enter(operationID: "a")
        pressure.enter(operationID: "b")
        XCTAssertEqual(pressure.snapshot().inUse, 2)
        pressure.leave(operationID: "a")
        let snapshot = pressure.snapshot()
        XCTAssertEqual(snapshot.inUse, 1)
        XCTAssertEqual(snapshot.peakInUse, 2, "peak must survive the release")
        XCTAssertEqual(snapshot.holders, ["b": 1], "holders must name what is still checked out")
    }

    /// Edge-triggered: a busy moment logs ONCE, not once per request. A leak —
    /// a floor that climbs and never falls — crosses once and stays crossed,
    /// which is precisely the signal we want to be able to distinguish.
    func testNearCeilingWarningIsEdgeTriggered() {
        let pressure = ConnectionPoolPressure(label: "test", ceiling: 4)   // threshold 3
        for index in 0..<3 { pressure.enter(operationID: "op\(index)") }
        XCTAssertEqual(pressure.snapshot().nearCeilingWarnings, 1, "crossing the threshold warns once")

        pressure.enter(operationID: "op3")
        XCTAssertEqual(
            pressure.snapshot().nearCeilingWarnings, 1,
            "staying above the threshold must not re-log per request"
        )

        // Drop back below, then cross again: a second, genuine crossing.
        pressure.leave(operationID: "op3")
        pressure.leave(operationID: "op2")
        XCTAssertEqual(pressure.snapshot().nearCeilingWarnings, 1)
        pressure.enter(operationID: "op4")
        XCTAssertEqual(pressure.snapshot().nearCeilingWarnings, 2, "re-crossing warns again")
    }

    func testPressureNeverGoesNegativeOnUnbalancedRelease() {
        let pressure = ConnectionPoolPressure(label: "test", ceiling: 8)
        pressure.leave(operationID: "never-entered")
        XCTAssertEqual(pressure.snapshot().inUse, 0)
    }

    func testResetClearsDerivedCountersButNotLiveUse() {
        let pressure = ConnectionPoolPressure(label: "test", ceiling: 4)
        for index in 0..<3 { pressure.enter(operationID: "op\(index)") }
        XCTAssertEqual(pressure.snapshot().nearCeilingWarnings, 1)
        pressure.reset()
        let snapshot = pressure.snapshot()
        XCTAssertEqual(snapshot.nearCeilingWarnings, 0)
        XCTAssertEqual(snapshot.inUse, 3, "reset must not lie about connections still checked out")
        XCTAssertEqual(snapshot.peakInUse, 3)
    }

    // MARK: - Segmentation wiring

    /// The core fix: a `.uds` client's stream transport and request transport
    /// must be BACKED BY DIFFERENT POOLS. Same pool = streams starve requests.
    @MainActor
    func testUDSStreamAndRequestTransportsUseSeparatePools() {
        let client = FicheroClient(transportMode: .uds(path: "/tmp/fichero-pool-test.sock"))

        let requestPressure = (client.transport as? PoolMonitoringTransport)?.pressure
        let streamPressure = (client.streamTransport as? PoolMonitoringTransport)?.pressure
        XCTAssertNotNil(requestPressure, "the UDS request transport must be pressure-accounted")
        XCTAssertNotNil(streamPressure, "the UDS stream transport must be pressure-accounted")
        XCTAssertFalse(
            requestPressure === streamPressure,
            "streams and requests must be accounted against SEPARATE pools"
        )
        XCTAssertEqual(requestPressure?.ceiling, LocalTransportPool.requestConnectionCeiling)
        XCTAssertEqual(streamPressure?.ceiling, LocalTransportPool.streamConnectionCeiling)

        XCTAssertFalse(
            FicheroClient.udsHTTPClient === FicheroClient.udsStreamHTTPClient,
            "the stream pool must be a DIFFERENT HTTPClient — one client is one pool"
        )
    }

    /// `.https` is segmented too: URLSession has the same shape of limit
    /// (`httpMaximumConnectionsPerHost` defaults to 6 on macOS).
    @MainActor
    func testHTTPSStreamAndRequestTransportsAreDistinct() {
        let requestTransport = FicheroClient.makeTransport(transportMode: .https, usage: .request)
        let streamTransport = FicheroClient.makeTransport(transportMode: .https, usage: .stream)
        let requestSession = (requestTransport as? URLSessionTransport)?.configuration.session
        let streamSession = (streamTransport as? URLSessionTransport)?.configuration.session
        XCTAssertNotNil(requestSession)
        XCTAssertNotNil(streamSession)
        XCTAssertFalse(requestSession === streamSession, "`.https` streams need their own session")
    }

    /// An explicitly injected session (mock / certificate-pinned pairing probe)
    /// must be honoured for BOTH usages — segmenting it away would silently drop
    /// the injection, which is the #4024 escape-to-the-real-network bug.
    @MainActor
    func testInjectedSessionIsHonouredForStreamsToo() {
        let injected = URLSession(configuration: .ephemeral)
        let client = FicheroClient(session: injected, transportMode: .https)
        XCTAssertTrue((client.transport as? URLSessionTransport)?.configuration.session === injected)
        XCTAssertTrue((client.streamTransport as? URLSessionTransport)?.configuration.session === injected)
    }

    // MARK: - N streams must not starve request traffic

    /// The regression this issue exists for: FOUR concurrent, never-ending
    /// stream subscriptions must not consume request capacity, and normal
    /// request traffic must still complete — with the near-ceiling tripwire
    /// staying silent on both pools.
    ///
    /// Driven through `PoolMonitoringTransport` (the exact decorator production
    /// wires onto the UDS transports) over a stub whose "streams" never end, so
    /// it is a real concurrency test with no socket and no engine.
    func testFourOpenStreamsDoNotStarveRequestTraffic() async throws {
        let requestPressure = ConnectionPoolPressure(
            label: "request", ceiling: LocalTransportPool.requestConnectionCeiling
        )
        let streamPressure = ConnectionPoolPressure(
            label: "stream", ceiling: LocalTransportPool.streamConnectionCeiling
        )
        let stub = StubPoolTransport()
        let requestTransport = PoolMonitoringTransport(wrapped: stub, pressure: requestPressure)
        let streamTransport = PoolMonitoringTransport(wrapped: stub, pressure: streamPressure)

        // Open four never-ending streams (four open libraries' worth) and hold
        // them for the duration of the request traffic below.
        let streamCount = 4
        let streamsOpen = StubPoolTransport.Latch(expected: streamCount)
        let streamTasks = (0..<streamCount).map { index in
            Task {
                let (_, body) = try await streamTransport.send(
                    StubPoolTransport.streamRequest, body: nil,
                    baseURL: StubPoolTransport.baseURL,
                    operationID: "changesStream.library\(index)"
                )
                await streamsOpen.signal()
                // Iterate forever — the stub never finishes this body.
                for try await _ in body! { }
            }
        }
        await streamsOpen.wait()
        XCTAssertEqual(streamPressure.snapshot().inUse, streamCount, "four streams held")
        XCTAssertEqual(
            requestPressure.snapshot().inUse, 0,
            "open streams must consume ZERO request-pool capacity — this is the bug"
        )

        // Now hammer the request pool while all four streams stay open.
        let requestCount = 40
        try await withThrowingTaskGroup(of: Int.self) { group in
            for index in 0..<requestCount {
                group.addTask {
                    let (response, body) = try await requestTransport.send(
                        StubPoolTransport.unaryRequest, body: nil,
                        baseURL: StubPoolTransport.baseURL,
                        operationID: "health.\(index % 4)"
                    )
                    if let body { for try await _ in body { } }
                    return response.status.code
                }
            }
            var completed = 0
            for try await status in group {
                XCTAssertEqual(status, 200)
                completed += 1
            }
            XCTAssertEqual(completed, requestCount, "every request must complete, not queue behind streams")
        }

        // The tripwire must NOT have fired: 4 streams and normal request traffic
        // are nowhere near either ceiling. If this ever fires, something is
        // holding connections it should have returned.
        XCTAssertEqual(
            streamPressure.snapshot().nearCeilingWarnings, 0,
            "four open streams must not approach the stream ceiling"
        )
        XCTAssertEqual(
            requestPressure.snapshot().nearCeilingWarnings, 0,
            "normal request traffic must not approach the request ceiling"
        )
        XCTAssertEqual(requestPressure.snapshot().inUse, 0, "every request returned its connection")

        for task in streamTasks { task.cancel() }
        _ = await withTaskGroup(of: Void.self) { group in
            for task in streamTasks { group.addTask { _ = await task.result } }
        }
    }

    // MARK: - Leak: a dropped stream must return its connection

    /// "Does a dropped stream return its connection before the retry opens
    /// another?" — mechanized. A stream whose body ends, throws, or is
    /// ABANDONED unread must leave the pool accounting at zero. The abandoned
    /// case is the one that matters: `ActivityStreamService.subscribeOnce`
    /// drops the line stream on a non-200 status and retries a second later.
    func testStreamBodyReleasesOnNormalEnd() async throws {
        let pressure = ConnectionPoolPressure(label: "stream", ceiling: 8)
        let transport = PoolMonitoringTransport(wrapped: StubPoolTransport(), pressure: pressure)
        let (_, body) = try await transport.send(
            StubPoolTransport.unaryRequest, body: nil,
            baseURL: StubPoolTransport.baseURL, operationID: "op"
        )
        XCTAssertEqual(pressure.snapshot().inUse, 1, "the connection is held while the body streams")
        for try await _ in body! { }
        XCTAssertEqual(pressure.snapshot().inUse, 0, "end of body returns the connection")
    }

    func testStreamBodyReleasesWhenItThrowsMidStream() async throws {
        let pressure = ConnectionPoolPressure(label: "stream", ceiling: 8)
        let transport = PoolMonitoringTransport(
            wrapped: StubPoolTransport(bodyFailsAfterChunks: 1), pressure: pressure
        )
        let (_, body) = try await transport.send(
            StubPoolTransport.streamRequest, body: nil,
            baseURL: StubPoolTransport.baseURL, operationID: "op"
        )
        do {
            for try await _ in body! { }
            XCTFail("the stub body must throw")
        } catch {
            // expected — this is the "activity stream dropped" path
        }
        XCTAssertEqual(pressure.snapshot().inUse, 0, "a dropped stream returns its connection")
    }

    /// The leak signature: repeated drop -> retry. If a dropped stream did not
    /// release, `inUse` would climb by one per cycle and the pool would be dry
    /// after `ceiling` retries. It must stay flat.
    func testRepeatedDropAndRetryDoesNotAccumulateConnections() async throws {
        let pressure = ConnectionPoolPressure(label: "stream", ceiling: 8)
        let transport = PoolMonitoringTransport(
            wrapped: StubPoolTransport(bodyFailsAfterChunks: 0), pressure: pressure
        )
        for cycle in 0..<20 {
            let (_, body) = try await transport.send(
                StubPoolTransport.streamRequest, body: nil,
                baseURL: StubPoolTransport.baseURL, operationID: "activityStream"
            )
            do { for try await _ in body! { } } catch { }
            XCTAssertEqual(
                pressure.snapshot().inUse, 0,
                "retry cycle \(cycle) leaked a connection — the pool would run dry"
            )
        }
        XCTAssertEqual(pressure.snapshot().nearCeilingWarnings, 0)
    }

    /// Abandoned WITHOUT ever being iterated — the non-200 path, where the
    /// caller throws before touching the body.
    func testAbandonedStreamBodyReleasesItsConnection() async throws {
        let pressure = ConnectionPoolPressure(label: "stream", ceiling: 8)
        let transport = PoolMonitoringTransport(wrapped: StubPoolTransport(), pressure: pressure)

        func openAndDrop() async throws {
            let (_, body) = try await transport.send(
                StubPoolTransport.streamRequest, body: nil,
                baseURL: StubPoolTransport.baseURL, operationID: "activityStream"
            )
            _ = body   // dropped, never iterated (the 403 / non-200 early-throw path)
        }
        try await openAndDrop()

        // The release rides the body's deinit, which is not synchronous with the
        // call returning; give the runtime a turn.
        for _ in 0..<100 where pressure.snapshot().inUse != 0 {
            try await Task.sleep(nanoseconds: 1_000_000)
        }
        XCTAssertEqual(
            pressure.snapshot().inUse, 0,
            "a response body dropped unread must still return its connection"
        )
    }

    /// A transport that fails to connect must not leave a phantom connection
    /// checked out — otherwise every failed reconnect would leak one.
    func testFailedSendReleasesImmediately() async {
        let pressure = ConnectionPoolPressure(label: "request", ceiling: 8)
        let transport = PoolMonitoringTransport(
            wrapped: StubPoolTransport(failsToConnect: true), pressure: pressure
        )
        do {
            _ = try await transport.send(
                StubPoolTransport.unaryRequest, body: nil,
                baseURL: StubPoolTransport.baseURL, operationID: "health"
            )
            XCTFail("the stub must fail to connect")
        } catch {
            // expected
        }
        XCTAssertEqual(pressure.snapshot().inUse, 0, "a failed dial holds nothing")
    }
}

// MARK: - Stub transport

/// A `ClientTransport` stub with two body shapes: a short unary body that ends,
/// and a "stream" body that never ends until the consumer stops. No socket, no
/// engine — it exists to exercise the pool-accounting decorator's bracketing.
private struct StubPoolTransport: ClientTransport {
    /// `nil` = the body ends normally; `n` = the body throws after `n` chunks.
    var bodyFailsAfterChunks: Int?
    var failsToConnect = false

    init(bodyFailsAfterChunks: Int? = nil, failsToConnect: Bool = false) {
        self.bodyFailsAfterChunks = bodyFailsAfterChunks
        self.failsToConnect = failsToConnect
    }

    static let baseURL = URL(string: "http://stub.local")!
    static let unaryRequest = HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/api/health")
    static var streamRequest: HTTPRequest {
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/api/changes/stream")
        request.headerFields[.accept] = "text/event-stream"
        return request
    }

    struct StubFailure: Error {}

    /// A simple counting latch so the test can wait for all N streams to open
    /// without sleeping on a wall clock.
    actor Latch {
        private var remaining: Int
        private var waiters: [CheckedContinuation<Void, Never>] = []
        init(expected: Int) { self.remaining = expected }
        func signal() {
            remaining -= 1
            guard remaining <= 0 else { return }
            let pending = waiters
            waiters = []
            for continuation in pending { continuation.resume() }
        }
        func wait() async {
            guard remaining > 0 else { return }
            await withCheckedContinuation { waiters.append($0) }
        }
    }

    func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        if failsToConnect { throw StubFailure() }
        let isStream = request.headerFields[.accept] == "text/event-stream"
        let failsAfter = bodyFailsAfterChunks
        let stream = AsyncThrowingStream<ArraySlice<UInt8>, any Error> { continuation in
            let task = Task {
                var emitted = 0
                while !Task.isCancelled {
                    if let failsAfter, emitted >= failsAfter {
                        continuation.finish(throwing: StubFailure())
                        return
                    }
                    continuation.yield(ArraySlice(": keepalive\n".utf8))
                    emitted += 1
                    if !isStream && emitted >= 1 {
                        continuation.finish()
                        return
                    }
                    // Long-lived stream: park until cancelled.
                    try? await Task.sleep(nanoseconds: 10_000_000)
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
        return (
            HTTPResponse(status: .ok),
            HTTPBody(stream, length: .unknown, iterationBehavior: .single)
        )
    }
}
