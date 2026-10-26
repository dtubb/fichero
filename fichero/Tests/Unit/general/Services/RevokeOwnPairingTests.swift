@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class RevokeSelfURLProtocol: URLProtocol {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var seen: [(method: String, path: String)] = []

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.hasPrefix("/api/pair/devices") == true
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.seen.append((request.httpMethod ?? "GET", request.url?.path ?? ""))
        let json = Self.status == 200 ? #"{"status":"ok"}"# : #"{"detail":"missing or invalid Authorization header"}"#
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// #6133 (`m2p.ios.forget-revokes-on-the-mac`): Forget This Mac asks the Mac to revoke this device's own pairing, with
/// no device id in the request, and carries on forgetting when the Mac says no or cannot be reached.
@MainActor
@Suite(.serialized)
struct RevokeOwnPairingTests {
    private func makeClient(status: Int) -> FicheroClient {
        RevokeSelfURLProtocol.status = status
        RevokeSelfURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RevokeSelfURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    @Test("the Mac saying yes is a revoked pairing, asked of the caller's own device only")
    func revokes() async {
        let revoked = await RemoteClientPairing.revokeOwnPairing(client: makeClient(status: 200))
        #expect(revoked)
        #expect(RevokeSelfURLProtocol.seen.map(\.path) == ["/api/pair/devices/revoke-self"])
        #expect(RevokeSelfURLProtocol.seen.map(\.method) == ["POST"])
    }

    @Test("a refusal is false, so the caller still forgets the pairing here")
    func refusal() async {
        let revoked = await RemoteClientPairing.revokeOwnPairing(client: makeClient(status: 401))
        #expect(!revoked)
    }
}
