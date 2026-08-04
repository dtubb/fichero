import XCTest
import AsyncHTTPClient
import NIOPosix
import OpenAPIRuntime
import OpenAPIURLSession
import OpenAPIAsyncHTTPClient
@testable import FicheroAPIClient

/// Verifies the pluggable-transport seam: `.https` keeps the existing
/// URLSession behavior byte-for-byte, and `.uds(path:)` selects the
/// AsyncHTTPClient transport pointed at the given AF_UNIX socket.
@MainActor
final class TransportModeTests: XCTestCase {

    // MARK: - Transport selection

    func testHTTPSModeYieldsURLSessionTransport() {
        let transport = FicheroClient.liveTransport(session: nil, transportMode: .https)
        XCTAssertTrue(
            transport is URLSessionTransport,
            "`.https` must stay on URLSessionTransport (unchanged behavior)"
        )
    }

    func testDefaultModeIsHTTPS() {
        // Default argument must preserve the pre-existing URLSession path.
        let transport = FicheroClient.liveTransport()
        XCTAssertTrue(transport is URLSessionTransport)
    }

    func testUDSModeYieldsAsyncHTTPClientTransport() {
        let transport = FicheroClient.liveTransport(
            session: nil,
            transportMode: .uds(path: "/tmp/fichero-test.sock")
        )
        // #4349 wraps the concrete transport in pool-pressure accounting; unwrap
        // before asserting which transport was actually selected.
        XCTAssertTrue(
            FicheroClient.underlyingTransport(transport) is AsyncHTTPClientTransport,
            "`.uds` must select the AsyncHTTPClient transport"
        )
    }

    func testUDSTransportDialsOverNIOPosixNotNetworkFramework() {
        // The regression this guards (the readiness-gate hang): AsyncHTTPClient's
        // default `HTTPClient.shared` uses `NIOTSEventLoopGroup` (Network.framework
        // NWConnection) on macOS, whose AF_UNIX flows intermittently fail to
        // establish under Xcode's debug launch. The UDS client MUST dial over a
        // NIOPosix (BSD-sockets) event loop — a plain POSIX connect(), like
        // `curl --unix-socket` and the engine. If someone reverts to `.shared`,
        // the loop becomes NIOTSEventLoopGroup and this fails.
        XCTAssertTrue(
            FicheroClient.udsHTTPClient.eventLoopGroup is MultiThreadedEventLoopGroup,
            "UDS must dial over NIOPosix (BSD sockets), not Network.framework — "
                + "else AF_UNIX connect starves under the Xcode debug launch"
        )
    }

    // MARK: - Server URL construction

    func testHTTPSServerURLIsUnchanged() {
        let base = URL(string: "https://127.0.0.1:8765")!
        let url = FicheroClient.makeServerURL(baseURL: base, transportMode: .https)
        XCTAssertEqual(url, base, "`.https` must leave the base URL untouched")
    }

    func testUDSServerURLEncodesSocketPathIntoAuthority() {
        let base = URL(string: "https://127.0.0.1:8765")!
        let socket = "/tmp/fichero-test.sock"
        let url = FicheroClient.makeServerURL(baseURL: base, transportMode: .uds(path: socket))

        XCTAssertEqual(url.scheme, "http+unix", "AsyncHTTPClient UDS scheme")
        // The socket path is percent-encoded into the authority ("/" -> "%2F"),
        // exactly like AsyncHTTPClient's URL(httpURLWithSocketPath:).
        XCTAssertEqual(url.absoluteString, "http+unix://%2Ftmp%2Ffichero-test.sock")
        // No path component, so the transport appends `/api/...` without a
        // stray leading double slash.
        XCTAssertTrue(url.path.isEmpty, "UDS base URL must carry an empty path")
    }

    // MARK: - Per-instance wiring (mixed transports in one app)

    func testConcurrentClientsCanUseDifferentTransports() {
        // A local UDS client and a remote HTTPS client must coexist; neither
        // construction should throw or share transport state.
        let local = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            transportMode: .uds(path: "/tmp/fichero-local.sock")
        )
        let remote = FicheroClient(
            baseURL: URL(string: "https://remote.example:8765")!,
            transportMode: .https
        )
        // `api` is non-optional; a successful construction is the assertion.
        XCTAssertEqual(local.baseURL.absoluteString, "https://127.0.0.1:8765")
        XCTAssertEqual(remote.baseURL.absoluteString, "https://remote.example:8765")
    }

    #if os(macOS)
    func testInMemoryServerURLIsStablePlaceholder() {
        // The in-process transport ignores host/port, so the server URL is a
        // fixed placeholder the generated client can append `/api/...` onto.
        let base = URL(string: "https://127.0.0.1:8765")!
        let url = FicheroClient.makeServerURL(baseURL: base, transportMode: .inMemory)
        XCTAssertEqual(url.absoluteString, "http://asgi.local")
    }
    #endif

    func testDefaultClientInitIsHTTPS() {
        // Existing call sites that don't pass a mode keep HTTPS behavior.
        let client = FicheroClient()
        XCTAssertEqual(client.baseURL.absoluteString, "https://127.0.0.1:8765")
    }

    // MARK: - UDS auth (review CRITICAL-1)

    func testUDSHostPrefersBootstrapToken() {
        // A UDS `http+unix://…` connection is local-owner → must authenticate
        // with the bootstrap token. Without this it is treated as a remote host,
        // which attaches no token and 401s every authenticated endpoint.
        XCTAssertTrue(
            AuthTokenMiddleware.prefersLocalhostEngineToken(
                hostString: "http+unix://%2Ftmp%2Ffichero.sock"
            ),
            "UDS (http+unix) must prefer the local bootstrap token"
        )
    }

    func testRemoteHTTPSHostStaysRemote() {
        // Preserve existing behavior: a genuine remote host is not bootstrap.
        XCTAssertFalse(
            AuthTokenMiddleware.prefersLocalhostEngineToken(
                hostString: "https://remote.example:8765"
            ),
            "A remote HTTPS host must not use the bootstrap token"
        )
    }

    func testLoopbackHTTPSHostStillPrefersBootstrapToken() {
        // Regression guard: the http+unix addition must not disturb loopback.
        XCTAssertTrue(
            AuthTokenMiddleware.prefersLocalhostEngineToken(
                hostString: "https://127.0.0.1:8765"
            )
        )
    }

    #if os(macOS)
    func testInMemoryHostPrefersBootstrapToken() {
        // #4052: the in-process `.inMemory` transport uses the placeholder host
        // `asgi.local` (see FicheroClient.makeServerURL). It is inherently
        // loopback — the request never leaves the process — so the full
        // `FicheroClient(transportMode: .inMemory)` path must attach the
        // bootstrap token. Without this, every authenticated in-process call
        // would 401 and the in-memory harness couldn't drive auth endpoints.
        XCTAssertTrue(
            AuthTokenMiddleware.prefersLocalhostEngineToken(
                hostString: "http://asgi.local"
            ),
            "`.inMemory` (asgi.local) must prefer the bootstrap token like loopback"
        )
    }
    #endif
}
