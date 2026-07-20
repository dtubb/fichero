import XCTest
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
        let transport = FicheroClient.makeTransport(session: nil, transportMode: .https)
        XCTAssertTrue(
            transport is URLSessionTransport,
            "`.https` must stay on URLSessionTransport (unchanged behavior)"
        )
    }

    func testDefaultModeIsHTTPS() {
        // Default argument must preserve the pre-existing URLSession path.
        let transport = FicheroClient.makeTransport()
        XCTAssertTrue(transport is URLSessionTransport)
    }

    func testUDSModeYieldsAsyncHTTPClientTransport() {
        let transport = FicheroClient.makeTransport(
            session: nil,
            transportMode: .uds(path: "/tmp/fichero-test.sock")
        )
        XCTAssertTrue(
            transport is AsyncHTTPClientTransport,
            "`.uds` must select the AsyncHTTPClient transport"
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

    func testDefaultClientInitIsHTTPS() {
        // Existing call sites that don't pass a mode keep HTTPS behavior.
        let client = FicheroClient()
        XCTAssertEqual(client.baseURL.absoluteString, "https://127.0.0.1:8765")
    }
}
