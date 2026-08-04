@testable import FicheroAPIClient
import Foundation
import Testing

@Suite("FicheroClient host rebinding")
struct FicheroClientTests {
    @Test("reconfigure updates the generated client host")
    @MainActor
    func reconfigureUpdatesBaseURL() {
        let originalURL = URL(string: "https://127.0.0.1:8765")!
        let remoteURL = URL(string: "https://host.tailnet.example")!
        let client = FicheroClient(baseURL: originalURL, libraryPath: "/tmp/Test.fichero")

        #expect(client.baseURL == originalURL)
        #expect(client.apiBaseURL == originalURL.appendingPathComponent("api"))
        #expect(client.currentLibraryPath == "/tmp/Test.fichero")

        client.reconfigure(baseURL: remoteURL)

        #expect(client.baseURL == remoteURL)
        #expect(client.apiBaseURL == remoteURL.appendingPathComponent("api"))
        #expect(client.currentLibraryPath == "/tmp/Test.fichero")
    }

    // MARK: - SPKI pinning seam (KG-gate removal, approved 2026-07-27)

    /// POSITIVE enforcement assertion: a client built for a remote host with
    /// an `expectedSPKIPin` must hold the explicitly-pinned session — this is
    /// the seam the retired `supportsAuthenticatedWebView()` gate claimed to
    /// protect. The pane's gate could be removed BECAUSE pinning is enforced
    /// here; if this ever stops holding, that removal is no longer safe.
    /// (Challenge-level accept/reject behaviour of the pinning delegates is
    /// covered by RemoteCertificatePinningTests.)
    @Test("a client built with an SPKI pin uses the explicitly-pinned session")
    @MainActor
    func clientWithSPKIPinUsesPinnedSession() throws {
        let pin = Data("remote-host-spki".utf8).base64EncodedString()
        let client = try FicheroClient(
            baseURL: URL(string: "https://100.99.1.2:8765")!,
            expectedSPKIPin: pin
        )

        let session = try #require(client.configuredSession)
        #expect(session.delegate is ExplicitPinnedSessionDelegate)
    }

    /// Without an explicit pin the client holds no custom session and its
    /// HTTPS transport falls back to `RemoteCertificatePinning
    /// .configuredSession`, whose delegate enforces PERSISTED pins
    /// dynamically — pinning-capable in both construction paths.
    @Test("a client built without a pin falls back to the dynamic-pinning session")
    @MainActor
    func clientWithoutPinFallsBackToDynamicPinning() throws {
        let client = try FicheroClient(
            baseURL: URL(string: "https://100.99.1.2:8765")!,
            expectedSPKIPin: nil
        )
        #expect(client.configuredSession == nil)

        // The fallback session `makeTransport` builds for `.https` clients:
        let fallback = RemoteCertificatePinning.configuredSession(configuration: .default)
        #expect(fallback.delegate is DynamicPinnedSessionDelegate)
    }
}
