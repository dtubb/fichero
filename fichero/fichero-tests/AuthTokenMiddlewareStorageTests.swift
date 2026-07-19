@testable import FicheroAPIClient
import Foundation
import Testing

@Suite("Auth token storage selection")
struct AuthTokenMiddlewareStorageTests {
    @Test(
        "localhost-class hosts use bootstrap token storage",
        arguments: [
            "https://127.0.0.1:8765",
            "https://127.2.3.4:8765",
            "https://localhost:8765",
            "https://[::1]:8765",
            "https://[0:0:0:0:0:0:0:1]:8765",
            "https://[::ffff:127.0.0.1]:8765",
            "",
            "   "
            // nil intentionally excluded: a nil host is NOT an explicit localhost —
            // it resolves through the saved fichero.engine.host default (UserDefaults),
            // so asserting it here is stateful/racy against suites that set that key
            // (e.g. WorkflowStreamConnectionTests). Production nil-resolution is
            // covered by prefersLocalhostEngineToken's own default path (#4016).
        ] as [String?]
    )
    func localhostHostsUseBootstrapStorage(hostString: String?) {
        #expect(AuthTokenMiddleware.tokenStorageKind(hostString: hostString) == .bootstrap)
        #expect(AuthTokenMiddleware.prefersLocalhostEngineToken(hostString: hostString))
    }

    @Test("loopback never prefers a saved login session")
    func loopbackDoesNotPreferSavedSession() {
        #expect(AuthTokenMiddleware.prefersLocalhostEngineToken(hostString: "https://127.0.0.1:8765"))
        #expect(AuthTokenMiddleware.prefersLocalhostEngineToken(hostString: "https://localhost:8765"))
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

    @Test("remote token keychain accounts normalize explicit default ports")
    func remoteTokenKeychainAccountsNormalizeExplicitDefaultPorts() {
        let httpsDefault = AuthTokenMiddleware.remoteTokenKeychainAccount(
            hostString: "https://host.tailnet.example:443/api"
        )
        let httpsImplicit = AuthTokenMiddleware.remoteTokenKeychainAccount(
            hostString: "https://host.tailnet.example"
        )
        let httpDefault = AuthTokenMiddleware.remoteTokenKeychainAccount(
            hostString: "http://host.tailnet.example:80"
        )
        let httpImplicit = AuthTokenMiddleware.remoteTokenKeychainAccount(
            hostString: "http://host.tailnet.example"
        )

        #expect(httpsDefault == httpsImplicit)
        #expect(httpDefault == httpImplicit)
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

    @Test("session token keychain accounts are host-specific and normalized")
    func sessionTokenKeychainAccountsAreHostSpecific() {
        let first = AuthTokenMiddleware.sessionTokenKeychainAccount(hostString: "https://host-one.tailnet.example")
        let second = AuthTokenMiddleware.sessionTokenKeychainAccount(hostString: "https://host-two.tailnet.example")

        #expect(first != second)
        #expect(first.hasPrefix("session-token|https://"))
        // Same normalization as the device token: default ports and path/query
        // collapse, so one engine maps to one session slot.
        let decorated = AuthTokenMiddleware.sessionTokenKeychainAccount(
            hostString: "https://host-one.tailnet.example:443/api?x=1#frag"
        )
        #expect(first == decorated)
    }

    @Test("session and remote device tokens never share a keychain account")
    func sessionAndRemoteTokensDoNotCollide() {
        let host = "https://host.tailnet.example"
        let session = AuthTokenMiddleware.sessionTokenKeychainAccount(hostString: host)
        let remote = AuthTokenMiddleware.remoteTokenKeychainAccount(hostString: host)
        #expect(session != remote)
    }

    @Test("login is unauthenticated so the sign-in request carries no stale token")
    func loginPathIsUnauthenticated() {
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/auth/login"))
        // /api/auth/me and /api/auth/logout still require a bearer token.
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/auth/me") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/auth/logout") == false)
    }

    @Test("unauthenticated paths require an exact path or path segment boundary")
    func unauthenticatedPathsRequireExactOrSegmentBoundary() {
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/health"))
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/health/"))
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/docs"))
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/docs/index.html"))

        // Regression (#2602): `/api/pair` itself must remain unauthenticated,
        // but its sub-paths require the engine bearer token.
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/pair"))
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/pair/code") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/pair/devices") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/pair/devices/abc/revoke") == false)

        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/healthcheck") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/healthz") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/api/docs") == false)
        #expect(AuthTokenMiddleware.isUnauthenticatedPath("/redocify") == false)
    }
}
