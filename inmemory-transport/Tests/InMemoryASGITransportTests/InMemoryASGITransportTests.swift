import HTTPTypes
import OpenAPIRuntime
import PythonKit
import XCTest

@testable import InMemoryASGITransport

final class InMemoryASGITransportTests: XCTestCase {

    // MARK: - (a) Unary: drive the real Fichero FastAPI app /api/health in-process.

    func testUnaryRealAppHealth() async throws {
        let app = ASGIAppLoader.importApp(module: "fichero.api.main", attribute: "app")
        let transport = InMemoryASGIClientTransport(app: app)

        let request = HTTPRequest(
            method: .get,
            scheme: "http",
            authority: "127.0.0.1",
            path: "/api/health"
        )

        let start = Date()
        let (response, body) = try await transport.send(
            request, body: nil, baseURL: URL(string: "http://127.0.0.1")!, operationID: "health"
        )
        let elapsed = Date().timeIntervalSince(start)

        XCTAssertEqual(response.status.code, 200, "health should return 200")

        let collected = try await Data(collecting: body ?? .init(""), upTo: 1 << 20)
        let json = String(decoding: collected, as: UTF8.self)
        print("[unary] /api/health in \(String(format: "%.3f", elapsed))s -> \(json.prefix(120))")
        XCTAssertTrue(json.contains("\"status\":\"healthy\""), "unexpected health body: \(json)")
    }

    // MARK: - (a2) AUTH: a real AUTHENTICATED endpoint returns 200 in-process.

    func testAuthenticatedEndpointReturns200() async throws {
        // Isolate app-state so we never touch the running engine's locked
        // app.duckdb or clobber its .api-key:
        //  - FICHERO_BASE_PATH (relocates app.duckdb) must be set in the ENV
        //    before import, because storage.settings is a module-level singleton.
        //  - HOME + FICHERO_BOOTSTRAP_TOKEN are read lazily on the first
        //    authenticated request, so setting them here (in-process) is in time.
        //    The bootstrap token is thus written under a temp HOME, not the real one.
        guard ProcessInfo.processInfo.environment["FICHERO_BASE_PATH"] != nil else {
            throw XCTSkip(
                "Set FICHERO_BASE_PATH to an isolated dir before running (avoids the "
                    + "running engine's app.duckdb lock). See run-tests.sh.")
        }
        let token = "inmemory-transport-test-\(UUID().uuidString)"
        let home = NSTemporaryDirectory() + "inmem-auth-home-\(UUID().uuidString)"
        try FileManager.default.createDirectory(
            atPath: home, withIntermediateDirectories: true)
        setenv("HOME", home, 1)
        setenv("FICHERO_BOOTSTRAP_TOKEN", token, 1)

        let app = ASGIAppLoader.importApp(module: "fichero.api.main", attribute: "app")
        let transport = InMemoryASGIClientTransport(app: app)
        let path = "/api/settings/model-profiles"  // requires auth; no library needed
        let baseURL = URL(string: "http://127.0.0.1")!

        // (i) Without a token: must NOT be 200 (proves the endpoint is protected).
        let unauth = HTTPRequest(
            method: .get, scheme: "http", authority: "127.0.0.1", path: path)
        let (unauthResp, _) = try await transport.send(
            unauth, body: nil, baseURL: baseURL, operationID: "modelProfiles")
        print("[auth] no-token status=\(unauthResp.status.code)")
        XCTAssertNotEqual(
            unauthResp.status.code, 200,
            "endpoint must reject unauthenticated in-process calls")

        // (ii) With the bootstrap token + the in-memory transport marker: 200.
        var authed = HTTPRequest(
            method: .get, scheme: "http", authority: "127.0.0.1", path: path)
        authed.headerFields[.authorization] = "Bearer \(token)"
        let (resp, body) = try await transport.send(
            authed, body: nil, baseURL: baseURL, operationID: "modelProfiles")
        let json = String(
            decoding: try await Data(collecting: body ?? .init(""), upTo: 1 << 20),
            as: UTF8.self)
        print("[auth] authed status=\(resp.status.code) body=\(json.prefix(80))")
        XCTAssertEqual(
            resp.status.code, 200,
            "authenticated endpoint should return 200 in-process, got "
                + "\(resp.status.code): \(json)")
    }

    // MARK: - (c) CONCURRENCY: a unary request completes while a stream drains.

    func testConcurrentUnaryDuringStreamDrain() async throws {
        // Slow SSE-like app: head immediately, then 3 chunks 0.4s apart (~1.2s).
        let slowApp = ASGIAppLoader.execApp(
            #"""
            import asyncio
            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                for i in range(3):
                    await asyncio.sleep(0.4)
                    await send({"type": "http.response.body",
                                "body": f"s{i}".encode(), "more_body": i < 2})
            """#)
        // Fast app: head + one body immediately, no delay.
        let fastApp = ASGIAppLoader.execApp(
            #"""
            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"fast", "more_body": False})
            """#)

        let slow = InMemoryASGIClientTransport(app: slowApp)
        let fast = InMemoryASGIClientTransport(app: fastApp)
        let baseURL = URL(string: "http://127.0.0.1")!
        let req = { (p: String) in
            HTTPRequest(method: .get, scheme: "http", authority: "127.0.0.1", path: p)
        }

        // Start consuming the slow stream in the background; record chunk times.
        let slowStart = Date()
        let slowTask = Task<[Double], Error> {
            let (_, body) = try await slow.send(
                req("/slow"), body: nil, baseURL: baseURL, operationID: "slow")
            var stamps: [Double] = []
            for try await chunk in body ?? .init("") {
                _ = chunk
                stamps.append(Date().timeIntervalSince(slowStart))
            }
            return stamps
        }

        // Let the slow stream get mid-drain (past its first 0.4s chunk, parked in
        // a blocking get() with the GIL released).
        try await Task.sleep(nanoseconds: 600_000_000)  // 0.6s

        // Now fire a unary request and time it. If the drain serialized the single
        // worker, this would block until the stream finished (~1.2s). It must not.
        let unaryStart = Date()
        let (uResp, uBody) = try await fast.send(
            req("/fast"), body: nil, baseURL: baseURL, operationID: "fast")
        let uData = try await Data(collecting: uBody ?? .init(""), upTo: 1 << 20)
        let unaryElapsed = Date().timeIntervalSince(unaryStart)
        let sinceSlowStart = Date().timeIntervalSince(slowStart)

        XCTAssertEqual(uResp.status.code, 200)
        XCTAssertEqual(String(decoding: uData, as: UTF8.self), "fast")
        print(String(
            format: "[concur] unary completed in %.3fs (at +%.2fs into the slow stream)",
            unaryElapsed, sinceSlowStart))

        // Unary must complete promptly while the ~1.2s slow stream is still going.
        XCTAssertLessThan(
            unaryElapsed, 0.30,
            "unary took \(unaryElapsed)s — the stream drain serialized the worker")
        XCTAssertLessThan(
            sinceSlowStart, 1.0,
            "unary finished at +\(sinceSlowStart)s — slow stream should still be draining")

        let slowStamps = try await slowTask.value
        XCTAssertEqual(slowStamps.count, 3, "slow stream should emit 3 chunks")
        XCTAssertGreaterThan(
            slowStamps.last ?? 0, 1.0, "slow stream should really take ~1.2s")
    }

    // MARK: - (d) CANCELLATION: dropping the stream stops the drain thread.

    func testStreamCancellationStopsDrain() async throws {
        // App that emits one chunk then would block "forever" (10s) before the next.
        let app = ASGIAppLoader.execApp(
            #"""
            import asyncio
            async def app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"first", "more_body": True})
                await asyncio.sleep(10.0)
                await send({"type": "http.response.body", "body": b"never", "more_body": False})
            """#)
        let drainEnded = expectation(description: "drain thread exited after cancellation")
        let transport = InMemoryASGIClientTransport(app: app, onDrainEnd: { drainEnded.fulfill() })

        // Read the first chunk, then let the response body go out of scope. When
        // the HTTPBody (and its underlying AsyncThrowingStream) is released without
        // being fully consumed, onTermination fires -> DrainControl.cancel(), which
        // wakes the drain thread out of its (10s) blocking get() and stops it.
        func consumeFirstChunkThenDrop() async throws {
            let (resp, body) = try await transport.send(
                HTTPRequest(method: .get, scheme: "http", authority: "127.0.0.1", path: "/sse"),
                body: nil, baseURL: URL(string: "http://127.0.0.1")!, operationID: "sse")
            XCTAssertEqual(resp.status.code, 200)
            let unwrapped = try XCTUnwrap(body)
            for try await chunk in unwrapped {
                XCTAssertEqual(String(decoding: chunk, as: UTF8.self), "first")
                break
            }
            // resp/body/unwrapped released at return -> stream termination.
        }
        try await consumeFirstChunkThenDrop()

        // The drain must exit promptly — far sooner than the app's 10s sleep —
        // proving cancellation stopped it rather than leaking for the SSE lifetime.
        await fulfillment(of: [drainEnded], timeout: 5.0)
        print("[cancel] drain thread exited after stream was dropped (< 5s, not 10s)")
    }

    // MARK: - (b) Streaming: prove chunks arrive INCREMENTALLY, not buffered.

    func testStreamingIsIncremental() async throws {
        // Synthetic ASGI app: 3 body chunks, ~0.3s apart, more_body:true between them.
        let synthApp = ASGIAppLoader.execApp(
            #"""
            import asyncio

            INTERVAL = 0.3

            async def app(scope, receive, send):
                assert scope["type"] == "http"
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/event-stream")],
                })
                for i in range(3):
                    await asyncio.sleep(INTERVAL)
                    await send({
                        "type": "http.response.body",
                        "body": f"chunk{i}".encode(),
                        "more_body": i < 2,
                    })
            """#
        )

        let transport = InMemoryASGIClientTransport(app: synthApp)
        let request = HTTPRequest(
            method: .get, scheme: "http", authority: "127.0.0.1", path: "/stream"
        )

        let start = Date()
        let (response, body) = try await transport.send(
            request, body: nil, baseURL: URL(string: "http://127.0.0.1")!, operationID: "stream"
        )
        XCTAssertEqual(response.status.code, 200)

        var arrivals: [(text: String, at: TimeInterval)] = []
        let unwrapped = try XCTUnwrap(body)
        for try await chunk in unwrapped {
            let t = Date().timeIntervalSince(start)
            let text = String(decoding: chunk, as: UTF8.self)
            arrivals.append((text, t))
            print(String(format: "[stream] +%.2fs  %@", t, text))
        }

        // Content correctness.
        XCTAssertEqual(arrivals.map(\.text), ["chunk0", "chunk1", "chunk2"])

        // THE KEY ASSERTION: chunks are surfaced incrementally, not all at the end.
        // With a buffering transport, every arrival timestamp would be ~identical
        // (all at ~0.9s). With true streaming they are spaced ~0.3s apart.
        let interval = 0.3
        let firstArrival = arrivals[0].at
        let lastArrival = arrivals[2].at

        // First chunk must arrive well before the last — at least ~2 intervals earlier.
        let gap = lastArrival - firstArrival
        print(String(format: "[stream] first=%.2fs last=%.2fs gap=%.2fs", firstArrival, lastArrival, gap))
        XCTAssertGreaterThan(
            gap, interval * 1.5,
            "chunk 1 must arrive well before chunk 3 (gap \(gap)s) — proves non-buffering"
        )

        // First chunk should arrive around one interval, not after the whole app ran.
        XCTAssertLessThan(
            firstArrival, interval * 2.0,
            "first chunk arrived at \(firstArrival)s — too late, looks buffered"
        )

        // Successive gaps should each be ~one interval (loose bounds for CI jitter).
        let gap01 = arrivals[1].at - arrivals[0].at
        let gap12 = arrivals[2].at - arrivals[1].at
        XCTAssertGreaterThan(gap01, interval * 0.5, "gap0->1 too small: \(gap01)s")
        XCTAssertGreaterThan(gap12, interval * 0.5, "gap1->2 too small: \(gap12)s")
    }
}
