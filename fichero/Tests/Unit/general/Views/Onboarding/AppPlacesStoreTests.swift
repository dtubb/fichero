@testable import Fichero
import FicheroAPIClient
import XCTest

/// `source.onboard.places-cap-projects` (#5828): a refused Continue on AI and ML Models says why on screen, never nothing.
@MainActor
final class AppPlacesStoreTests: XCTestCase {
    private final class Refusing: URLProtocol {
        nonisolated(unsafe) static var status = 400
        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            guard let url = request.url,
                  let response = HTTPURLResponse(url: url, statusCode: Self.status, httpVersion: "HTTP/1.1",
                                                 headerFields: ["Content-Type": "application/json"]) else { return }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data("{}".utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    func testARefusedKeepAnswerLeavesAnErrorSentenceShown() async {
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Refusing.self]
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!,
                                   libraryPath: "/tmp/AppPlacesStoreTests.fichero",
                                   session: URLSession(configuration: configuration))
        let store = AppPlacesStore(client: client)
        let moved = await store.keepAnswer()
        XCTAssertFalse(moved)
        XCTAssertFalse(store.answered)
        XCTAssertFalse((store.errorMessage ?? "").isEmpty, "a refused Continue must say why")
    }
}
