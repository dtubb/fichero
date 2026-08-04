import XCTest
import Foundation
import NIOCore
import OpenAPIRuntime
import OpenAPIAsyncHTTPClient
import AsyncHTTPClient
@testable import FicheroAPIClient

/// #4379 — the whole-request deadline applied to the local (`.uds`) transport.
///
/// The bug: `AsyncHTTPClientTransport(configuration: .init(client: client))`
/// passed no `timeout:`, so it inherited the package default of one minute.
/// That default is handed to `HTTPClient.execute(_:timeout:)`, which deadlines
/// the WHOLE request *including reading the complete response body* — and an
/// SSE body is never complete until the subscription ends. Every stream over
/// UDS was therefore killed at exactly 60 seconds with
/// `HTTPClientError.deadlineExceeded`, surfacing as "Lost connection to the
/// Fichero server…". A named-entity extraction that ran longer than a minute
/// could not survive its own duration.
///
/// The trap is that the omission was invisible at the seam:
/// `LocalTransportPool.configuration(softLimit:)` correctly sets *no* read
/// timeout on the `HTTPClient` and says so in a comment — and the transport one
/// layer up silently overrode that intent. So these tests assert on the value
/// that actually reaches the transport, not merely on the constants.
///
/// Pure and headless: no socket, no engine.
final class RequestDeadlineTests: XCTestCase {

    private static let inheritedDefault: TimeAmount = .minutes(1)

    // MARK: - The constants are chosen, and the two populations differ

    /// The regression that produced the incident. If this fails, streams are
    /// back on a one-minute leash.
    func testStreamDeadlineIsNotTheInheritedOneMinuteDefault() {
        XCTAssertNotEqual(
            LocalTransportPool.streamDeadline, Self.inheritedDefault,
            """
            A stream deadline of one minute is the #4379 bug: an SSE body is \
            never "complete", so the deadline fires on every healthy \
            subscription that outlives a minute.
            """
        )
    }

    /// Requests and streams have opposite lifetimes, so one deadline cannot be
    /// right for both. This is the same reasoning that segmented the pools.
    func testStreamsGetAMuchLongerDeadlineThanRequests() {
        XCTAssertGreaterThan(
            LocalTransportPool.streamDeadline.nanoseconds,
            LocalTransportPool.requestDeadline.nanoseconds,
            "a parked SSE subscription is healthy; a slow request is not"
        )
    }

    /// A stream must outlive any plausible working session, because the only
    /// honest bound on one is "as long as the library is open".
    func testStreamDeadlineOutlivesARealisticSession() {
        XCTAssertGreaterThan(
            LocalTransportPool.streamDeadline.nanoseconds,
            TimeAmount.hours(8).nanoseconds,
            "a library open across a working day must not drop its streams"
        )
    }

    /// Still bounded, for the same reason the pool ceilings are: an unbounded
    /// deadline turns a hang into a silence.
    func testRequestDeadlineStaysBounded() {
        XCTAssertGreaterThan(LocalTransportPool.requestDeadline.nanoseconds, 0)
        XCTAssertLessThanOrEqual(
            LocalTransportPool.requestDeadline.nanoseconds,
            TimeAmount.minutes(5).nanoseconds,
            "a local request that runs for minutes should fail loudly, not hang"
        )
    }

    // MARK: - The deadline actually reaches the transport

    /// The guardrail that would have caught the original defect: the bug was a
    /// MISSING argument at the call site, which no assertion on the constants
    /// alone can detect. These read the timeout off the transport that
    /// `liveTransport` actually built.

    func testUDSStreamTransportCarriesTheStreamDeadline() throws {
        let timeout = try Self.deadline(ofTransportFor: .stream)
        XCTAssertEqual(
            timeout, LocalTransportPool.streamDeadline,
            """
            The stream transport is not carrying `streamDeadline` — the \
            `timeout:` argument was most likely dropped at the `liveTransport` \
            call site, which is exactly how #4379 happened.
            """
        )
        XCTAssertNotEqual(
            timeout, Self.inheritedDefault,
            "an omitted `timeout:` silently reinstates the one-minute default"
        )
    }

    func testUDSRequestTransportCarriesTheRequestDeadline() throws {
        let timeout = try Self.deadline(ofTransportFor: .request)
        XCTAssertEqual(timeout, LocalTransportPool.requestDeadline)
    }

    func testTheTwoUDSTransportsDoNotShareADeadline() throws {
        let request = try Self.deadline(ofTransportFor: .request)
        let stream = try Self.deadline(ofTransportFor: .stream)
        XCTAssertNotEqual(
            request, stream,
            "segmenting the pools but sharing one deadline leaves #4379 open"
        )
    }

    // MARK: - Helper

    /// The whole-request deadline the `.uds` transport for `usage` was built
    /// with, unwrapped from the pool-accounting decorator.
    private static func deadline(
        ofTransportFor usage: FicheroClient.TransportUsage
    ) throws -> TimeAmount {
        let transport = FicheroClient.liveTransport(
            transportMode: .uds(path: "/tmp/fichero-deadline-test.sock"),
            usage: usage
        )
        let underlying = FicheroClient.underlyingTransport(transport)
        let httpTransport = try XCTUnwrap(
            underlying as? AsyncHTTPClientTransport,
            "the `.uds` transport must be an AsyncHTTPClientTransport"
        )
        return httpTransport.configuration.timeout
    }
}
