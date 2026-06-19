@testable import FicheroAPIClient
import Foundation
import Testing

@Suite("Auth token storage selection")
struct AuthTokenMiddlewareStorageTests {
    @Test(
        "localhost-class hosts use bootstrap token storage",
        arguments: [
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "http://[::1]:8765",
            nil
        ] as [String?]
    )
    func localhostHostsUseBootstrapStorage(hostString: String?) {
        #expect(AuthTokenMiddleware.tokenStorageKind(hostString: hostString) == .bootstrap)
        #expect(AuthTokenMiddleware.prefersLocalhostEngineToken(hostString: hostString))
    }

    @Test(
        "remote hosts use remote token storage",
        arguments: [
            "http://100.119.93.85:8765",
            "https://host.tailnet.example",
            "https://fichero.example.com"
        ]
    )
    func remoteHostsUseRemoteStorage(hostString: String) {
        #expect(AuthTokenMiddleware.tokenStorageKind(hostString: hostString) == .remote)
        #expect(AuthTokenMiddleware.prefersLocalhostEngineToken(hostString: hostString) == false)
    }

    @Test("remote token filenames are host-specific and normalized")
    func remoteTokenFilenamesAreHostSpecific() {
        let first = AuthTokenMiddleware.remoteTokenFileName(hostString: "https://host-one.tailnet.example")
        let second = AuthTokenMiddleware.remoteTokenFileName(hostString: "https://host-two.tailnet.example")

        #expect(first != second)
        #expect(first.hasPrefix(".remote-api-key-"))
        #expect(second.hasPrefix(".remote-api-key-"))
    }

    @Test("bootstrap and remote token paths stay distinct")
    func bootstrapAndRemoteTokenPathsStayDistinct() {
        let bootstrap = AuthTokenMiddleware.bootstrapTokenFileURL()
        let remote = AuthTokenMiddleware.remoteTokenFileURL(hostString: "https://host.tailnet.example")

        #expect(bootstrap != nil)
        #expect(remote != nil)
        #expect(bootstrap != remote)
        #expect(remote?.lastPathComponent == AuthTokenMiddleware.remoteTokenFileName(hostString: "https://host.tailnet.example"))
    }
}
