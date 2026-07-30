import AsyncHTTPClient
import Foundation
import HTTPTypes
import NIOCore
import OpenAPIRuntime
import OSLog

/// Connection-pool sizing, segmentation and pressure accounting for the local
/// (`.uds`) transport (#4349).
///
/// ## What was actually broken
///
/// Long-lived SSE subscriptions (activity stream, library change stream,
/// workflow execution stream) and short request/response calls drew from the
/// SAME `HTTPClient` connection pool. Those two populations have opposite
/// lifetimes: a request holds a connection for milliseconds, a stream holds one
/// for as long as the library is open. Stream count grows with the number of
/// open libraries, so past a handful of libraries the streams pinned every
/// connection in the pool and ordinary request traffic queued until it timed
/// out. That is the design error — sharing one pool between the two — and no
/// pool size fixes it, because any fixed number is exhausted by enough streams.
///
/// So: ``streamHTTPClient`` and ``requestHTTPClient`` are two distinct
/// `HTTPClient` instances with two distinct pools. Streams can no longer starve
/// requests no matter how many libraries are open.
///
/// ## Why the numbers
///
/// AsyncHTTPClient's default `concurrentHTTP1ConnectionsPerHostSoftLimit` is 8.
/// Eight is *inherited, not chosen*: it is a politeness/TLS-amortization default
/// aimed at remote third-party servers on shared infrastructure. None of that
/// applies to an AF_UNIX socket to our own single-tenant engine on the same
/// machine — there is no handshake to amortize, no shared host to be polite to,
/// and a UDS connection costs a file descriptor and a few kilobytes.
///
/// The relevant ceiling is the SERVER's, not the socket's. The engine runs
/// `uvicorn ... workers=1` (see `fichero_server/__main__.py`), i.e. ONE event
/// loop, and blocking DuckDB/file work is dispatched to a bounded thread pool:
/// `asyncio.to_thread` uses the loop's default `ThreadPoolExecutor`
/// (`min(32, cpu_count + 4)` — 14 on a 10-core Mac), and Starlette's sync
/// endpoints use AnyIO's 40-token thread limiter. So the server can make
/// genuine concurrent progress on roughly 14-40 blocking operations; client
/// connections past that only relocate the queue from the client to the server.
///
/// Peak legitimate demand on the REQUEST pool is a burst, not a steady state:
/// WebKit resource loads for a reader page plus store refreshes on a library
/// switch. ``requestConnectionCeiling`` is set comfortably above the server's
/// own ceiling so the client is never the bottleneck, and no higher, because
/// extra connections buy nothing past that point.
///
/// ## Why a ceiling at all
///
/// The ceiling is a LEAK DETECTOR, not a throttle. This whole bug was
/// diagnosable only because a limit was hit *loudly*: the pool ran dry and
/// requests timed out. Unbounded growth would have hidden a connection leak
/// until per-process file-descriptor exhaustion — a stranger failure, much
/// later, far from the cause. ``ConnectionPoolPressure`` makes that even
/// louder: it warns while there is still headroom, naming the count and the
/// operations holding the connections, so hitting the ceiling teaches us there
/// is a leak instead of silently degrading.
public enum LocalTransportPool {

    // MARK: - Ceilings

    /// Per-host soft limit for the short-lived request/response pool.
    ///
    /// 64: comfortably above the engine's own concurrency ceiling (one uvicorn
    /// worker; ~14-40 concurrent blocking operations, see the type doc), so the
    /// client never becomes the bottleneck, while still bounded so a leak shows
    /// up as a loud timeout rather than fd exhaustion.
    public static let requestConnectionCeiling = 64

    /// Per-host soft limit for the long-lived SSE/stream pool.
    ///
    /// 32: a library holds at most a handful of concurrent subscriptions in
    /// practice (change stream + activity stream, plus one per running workflow
    /// execution), so 32 covers roughly a dozen simultaneously-open libraries.
    /// Separate from the request pool, so exhausting it degrades live updates
    /// only — request traffic is untouched.
    public static let streamConnectionCeiling = 32

    /// Fraction of the ceiling at which the tripwire fires. Warning at 75%
    /// leaves headroom to capture a diagnostic *before* traffic starts queuing.
    public static let nearCeilingFraction = 0.75

    /// How long an idle pooled connection is kept. Local sockets are cheap;
    /// keeping them a minute avoids reconnect churn during a library switch.
    static let idleTimeout: TimeAmount = .seconds(60)

    // MARK: - Request deadlines (#4379)

    /// Whole-request deadline for short request/response calls.
    ///
    /// 60 seconds — deliberately the SAME number
    /// `AsyncHTTPClientTransport.Configuration` defaults to, because there is
    /// no evidence a local request legitimately needs longer, and inventing a
    /// bigger number would only convert a loud failure into a long hang. What
    /// changes is that it is now *chosen and named* rather than inherited, so
    /// the stream deadline below can differ from it deliberately.
    static let requestDeadline: TimeAmount = .seconds(60)

    /// Whole-"request" deadline for long-lived SSE subscriptions.
    ///
    /// ## What was actually broken (#4379)
    ///
    /// `AsyncHTTPClientTransport.Configuration.init(client:timeout:)` defaults
    /// `timeout` to one minute, and the transport passes it to
    /// `HTTPClient.execute(_:timeout:)` — which deadlines the WHOLE request,
    /// *including reading the complete response body*. An SSE body is never
    /// "complete" until the subscription ends, so every stream over `.uds` was
    /// killed at exactly 60 seconds with `HTTPClientError.deadlineExceeded`,
    /// surfacing as "Lost connection to the Fichero server…". Watching a
    /// workflow run longer than a minute — a named-entity extraction over real
    /// documents — could not survive its own duration.
    ///
    /// The call site passed no `timeout:`, so the deadline was invisible at
    /// the seam: ``configuration(softLimit:)`` correctly sets no read timeout
    /// on the `HTTPClient`, and that intent was silently defeated one layer up
    /// by the transport's default.
    ///
    /// ## Why this value
    ///
    /// A deadline is the wrong instrument for a stream: an idle SSE
    /// subscription is healthy, not stalled, and the only honest bound on one
    /// is "as long as the library is open". The transport API takes a
    /// `TimeAmount` and offers no "no deadline", so this is the largest value
    /// that still expresses a bound — a full day, far longer than any session,
    /// and long enough that reaching it means something is genuinely wrong
    /// rather than merely quiet. Stream loss is already reconciled (#4346), so
    /// a re-dial at that point is a recovery, not a failure.
    static let streamDeadline: TimeAmount = .hours(24)

    /// The whole-request deadline for a given traffic population. Pure, so the
    /// two populations' deadlines are assertable without opening a socket.
    static func deadline(for usage: FicheroClient.TransportUsage) -> TimeAmount {
        switch usage {
        case .request: return requestDeadline
        case .stream: return streamDeadline
        }
    }

    /// The in-use count at or above which ``ConnectionPoolPressure`` warns.
    /// Pure arithmetic, kept separate so it is unit-testable without a socket.
    ///
    /// Always at least 1 and never above `ceiling`, so a nonsense ceiling can
    /// never disable the tripwire outright.
    public static func nearCeilingThreshold(ceiling: Int) -> Int {
        guard ceiling > 0 else { return 1 }
        let scaled = Int((Double(ceiling) * nearCeilingFraction).rounded(.up))
        return min(max(scaled, 1), ceiling)
    }

    /// Whether `inUse` connections against `ceiling` is close enough to warrant
    /// the near-ceiling warning.
    public static func isNearCeiling(inUse: Int, ceiling: Int) -> Bool {
        inUse >= nearCeilingThreshold(ceiling: ceiling)
    }

    // MARK: - Pressure accounting

    /// Live pressure on the short-lived request pool.
    public static let requestPressure = ConnectionPoolPressure(
        label: "request",
        ceiling: requestConnectionCeiling
    )

    /// Live pressure on the long-lived stream pool.
    public static let streamPressure = ConnectionPoolPressure(
        label: "stream",
        ceiling: streamConnectionCeiling
    )

    // MARK: - Clients

    /// `HTTPClient` configuration for a local UDS pool with an explicit ceiling.
    static func configuration(softLimit: Int) -> HTTPClient.Configuration {
        var configuration = HTTPClient.Configuration()
        configuration.connectionPool = HTTPClient.Configuration.ConnectionPool(
            idleTimeout: idleTimeout,
            concurrentHTTP1ConnectionsPerHostSoftLimit: softLimit
        )
        // No read timeout: an idle SSE subscription is healthy, not stalled, and
        // a read deadline would kill every quiet stream. Connect timeouts stay at
        // AsyncHTTPClient's default.
        //
        // NOTE (#4379): this alone does NOT make streams deadline-free. The
        // `AsyncHTTPClientTransport` wrapping this client applies its own
        // whole-request deadline on top, and its default of one minute was
        // silently defeating the intent above. See ``streamDeadline`` — the
        // deadline must be set at the transport, not only omitted here.
        return configuration
    }

    /// URLSession per-host connection cap for the `.https` transport. URLSession
    /// has the same shape of problem (`httpMaximumConnectionsPerHost` defaults
    /// to 6 on macOS), so the `.https` path is segmented and sized the same way.
    static func urlSessionConfiguration(maximumConnectionsPerHost: Int) -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.default
        configuration.httpMaximumConnectionsPerHost = maximumConnectionsPerHost
        return configuration
    }
}

// MARK: - ConnectionPoolPressure

/// Tracks how many connections of one pool are currently in use, warns when the
/// count approaches the pool's ceiling, and exposes a queryable snapshot.
///
/// Edge-triggered: the warning fires when the in-use count *crosses* the
/// threshold going up, and re-arms only after it falls back below. A busy
/// moment therefore logs once, not once per request, and
/// ``Snapshot/nearCeilingWarnings`` counts genuine crossings — which is exactly
/// the signal a leak produces (a monotonically climbing floor that crosses once
/// and never re-arms).
///
/// `@unchecked Sendable` with an `NSLock`: the transport dials off the main
/// actor and the counters must be readable synchronously from tests.
public final class ConnectionPoolPressure: @unchecked Sendable {

    /// A point-in-time view of one pool's pressure.
    public struct Snapshot: Sendable, Equatable {
        /// Which pool ("request" / "stream").
        public let label: String
        /// Connections currently checked out.
        public let inUse: Int
        /// Highest `inUse` seen since the last ``ConnectionPoolPressure/reset()``.
        public let peakInUse: Int
        /// The pool's configured ceiling.
        public let ceiling: Int
        /// How many times the near-ceiling tripwire fired.
        public let nearCeilingWarnings: Int
        /// Operations currently holding connections, highest count first.
        public let holders: [String: Int]
    }

    /// Which pool this tracks.
    public let label: String

    /// The pool's configured connection ceiling.
    public let ceiling: Int

    private let lock = NSLock()
    private var inUse = 0
    private var peakInUse = 0
    private var nearCeilingWarnings = 0
    private var warningArmed = true
    private var holders: [String: Int] = [:]

    private let log = Logger(subsystem: "app.fichero.fichero", category: "ConnectionPool")

    init(label: String, ceiling: Int) {
        self.label = label
        self.ceiling = ceiling
    }

    /// Check a connection out on behalf of `operationID`.
    func enter(operationID: String) {
        lock.lock()
        inUse += 1
        peakInUse = max(peakInUse, inUse)
        holders[operationID, default: 0] += 1
        let current = inUse
        let shouldWarn = warningArmed && LocalTransportPool.isNearCeiling(inUse: current, ceiling: ceiling)
        if shouldWarn {
            warningArmed = false
            nearCeilingWarnings += 1
        }
        let snapshotHolders = shouldWarn ? holders : [:]
        lock.unlock()

        guard shouldWarn else { return }
        // Name the count AND what holds them: a pool that fills with one
        // operationID repeated is a leak; a pool that fills with a spread of
        // operations is genuine load.
        let breakdown = snapshotHolders
            .sorted { ($0.value, $0.key) > ($1.value, $1.key) }
            .prefix(5)
            .map { "\($0.key)=\($0.value)" }
            .joined(separator: ", ")
        log.warning(
            """
            \(self.label, privacy: .public) connection pool near ceiling: \
            \(current, privacy: .public)/\(self.ceiling, privacy: .public) in use — \
            held by [\(breakdown, privacy: .public)]. \
            The ceiling is a leak detector: a count that climbs and never falls \
            means connections are not being returned.
            """
        )
    }

    /// Return the connection checked out by `operationID`.
    func leave(operationID: String) {
        lock.lock()
        inUse = max(0, inUse - 1)
        if let held = holders[operationID] {
            if held <= 1 { holders.removeValue(forKey: operationID) } else { holders[operationID] = held - 1 }
        }
        if !LocalTransportPool.isNearCeiling(inUse: inUse, ceiling: ceiling) {
            warningArmed = true
        }
        lock.unlock()
    }

    /// A queryable view of this pool's pressure — the "cheap counter" half of
    /// the tripwire, so a test (or a support dump) can assert the warning did
    /// NOT fire rather than scraping logs.
    public func snapshot() -> Snapshot {
        lock.lock()
        defer { lock.unlock() }
        return Snapshot(
            label: label,
            inUse: inUse,
            peakInUse: peakInUse,
            ceiling: ceiling,
            nearCeilingWarnings: nearCeilingWarnings,
            holders: holders
        )
    }

    /// Reset the derived counters (peak / warnings). Does NOT touch `inUse`,
    /// which is owned by live traffic. For tests and diagnostics.
    public func reset() {
        lock.lock()
        peakInUse = inUse
        nearCeilingWarnings = 0
        warningArmed = !LocalTransportPool.isNearCeiling(inUse: inUse, ceiling: ceiling)
        lock.unlock()
    }
}

// MARK: - PoolMonitoringTransport

/// A `ClientTransport` decorator that brackets each request with
/// ``ConnectionPoolPressure`` accounting.
///
/// The bracket deliberately spans the RESPONSE BODY, not just `send(...)`.
/// `send` returns as soon as the response head is available; the underlying
/// connection is only returned to the pool once the body is fully read (or the
/// body is abandoned). Counting only `send` would under-report exactly the
/// population that caused #4349 — a long-lived SSE body whose head arrived
/// instantly and whose connection is then held for hours.
///
/// The release is idempotent and fires on all three exits: normal end-of-body,
/// a thrown error mid-body, and the consumer dropping the body without reading
/// it (via ``ConnectionReleaseToken``'s `deinit`). That last case is the one the
/// leak hunt was about: a dropped stream must give its connection back before
/// the retry opens another.
struct PoolMonitoringTransport: ClientTransport {
    let wrapped: any ClientTransport
    let pressure: ConnectionPoolPressure

    func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        pressure.enter(operationID: operationID)
        let token = ConnectionReleaseToken { [pressure] in pressure.leave(operationID: operationID) }

        let response: HTTPResponse
        let responseBody: HTTPBody?
        do {
            (response, responseBody) = try await wrapped.send(
                request, body: body, baseURL: baseURL, operationID: operationID
            )
        } catch {
            token.release()
            throw error
        }

        guard let responseBody else {
            token.release()
            return (response, nil)
        }
        return (
            response,
            HTTPBody(
                ReleasingByteSequence(upstream: responseBody, token: token),
                length: responseBody.length,
                iterationBehavior: responseBody.iterationBehavior
            )
        )
    }
}

/// A one-shot release latch. Releases on explicit ``release()`` or, failing
/// that, when the last reference goes away — so abandoning a response body can
/// never strand the accounting (or, in production, hide a stranded connection).
final class ConnectionReleaseToken: @unchecked Sendable {
    private let lock = NSLock()
    private var released = false
    private let onRelease: @Sendable () -> Void

    init(onRelease: @escaping @Sendable () -> Void) { self.onRelease = onRelease }

    func release() {
        lock.lock()
        let isFirst = !released
        released = true
        lock.unlock()
        if isFirst { onRelease() }
    }

    deinit { release() }
}

/// Wraps an `HTTPBody` and trips a ``ConnectionReleaseToken`` when iteration
/// ends — normally, by error, or by the body being dropped.
private struct ReleasingByteSequence: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>

    let upstream: HTTPBody
    let token: ConnectionReleaseToken

    struct AsyncIterator: AsyncIteratorProtocol {
        var upstream: HTTPBody.Iterator
        let token: ConnectionReleaseToken

        mutating func next() async throws -> ArraySlice<UInt8>? {
            do {
                let chunk = try await upstream.next()
                if chunk == nil { token.release() }
                return chunk
            } catch {
                token.release()
                throw error
            }
        }
    }

    func makeAsyncIterator() -> AsyncIterator {
        AsyncIterator(upstream: upstream.makeAsyncIterator(), token: token)
    }
}
