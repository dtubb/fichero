@testable import FicheroAPIClient
import Foundation
import Testing

@Suite("Auth token storage selection")
struct AuthTokenMiddlewareStorageTests {
    @Test(
        "localhost-class hosts use bootstrap token storage",
        arguments: [
            "http://127.0.0.1:8765",
            "http://127.2.3.4:8765",
            "http://localhost:8765",
            "http://[::1]:8765",
            "http://[0:0:0:0:0:0:0:1]:8765",
            "http://[::ffff:127.0.0.1]:8765",
            "",
            "   ",
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
            "https://fichero.example.com",
            "http://[2001:db8::ffff:127.0.0.1]:8765",
            "https://remote host/"
        ]
    )
    func remoteHostsUseRemoteStorage(hostString: String) {
        #expect(AuthTokenMiddleware.tokenStorageKind(hostString: hostString) == .remote)
        #expect(AuthTokenMiddleware.prefersLocalhostEngineToken(hostString: hostString) == false)
    }

    @Test("remote token keychain accounts are host-specific and normalized")
    func remoteTokenKeychainAccountsAreHostSpecific() {
        let first = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://host-one.tailnet.example")
        let second = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://host-two.tailnet.example")

        #expect(first != second)
        #expect(first.hasPrefix(".remote-api-key-"))
        #expect(second.hasPrefix(".remote-api-key-"))
    }

    @Test("bootstrap file storage and remote keychain routing stay distinct")
    func bootstrapFileStorageAndRemoteKeychainRoutingStayDistinct() {
        let bootstrap = AuthTokenMiddleware.bootstrapTokenFileURL()
        let remoteAccount = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://host.tailnet.example")

        #expect(bootstrap != nil)
        #expect(bootstrap?.lastPathComponent == ".api-key")
        #expect(remoteAccount == AuthTokenMiddleware.remoteTokenFileName(hostString: "https://host.tailnet.example"))
        #expect(bootstrap?.lastPathComponent != remoteAccount)
    }
}
