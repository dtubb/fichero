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
        #expect(first.hasPrefix("remote-device-token|https://"))
        #expect(second.hasPrefix("remote-device-token|https://"))
    }

    @Test("remote token keychain accounts do not collide on punctuation variants")
    func remoteTokenKeychainAccountsDoNotCollideOnPunctuationVariants() {
        let dash = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://a-b.example")
        let dot = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://a.b.example")
        let underscorePathLike = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://a_b.example")

        #expect(dash != dot)
        #expect(dash != underscorePathLike)
        #expect(dot != underscorePathLike)
    }

    @Test("remote token keychain accounts strip path query and fragment")
    func remoteTokenKeychainAccountsStripPathQueryAndFragment() {
        let root = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://host.tailnet.example/")
        let decorated = AuthTokenMiddleware.remoteTokenKeychainAccount(
            hostString: "https://host.tailnet.example/api?x=1#frag"
        )
        let differentHost = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://other.tailnet.example/")

        #expect(root == decorated)
        #expect(root != differentHost)
    }

    @Test("bootstrap file storage and remote keychain routing stay distinct")
    func bootstrapFileStorageAndRemoteKeychainRoutingStayDistinct() {
        let bootstrap = AuthTokenMiddleware.bootstrapTokenFileURL()
        let remoteAccount = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: "https://host.tailnet.example")

        #expect(bootstrap != nil)
        #expect(bootstrap?.lastPathComponent == ".api-key")
        #expect(remoteAccount == "remote-device-token|https://host.tailnet.example")
        #expect(bootstrap?.lastPathComponent != remoteAccount)
    }

    @Test("unauthenticated paths require an exact path or path segment boundary")
    func unauthenticatedPathsRequireExactOrSegmentBoundary() {
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/health"))
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/health/"))
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/docs"))
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/docs/index.html"))

        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/healthcheck") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/healthz") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/docs") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/redocify") == false)
    }
}
