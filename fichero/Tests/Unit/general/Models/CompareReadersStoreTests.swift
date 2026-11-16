@testable import Fichero
import FicheroAPIClient
import XCTest

/// `CompareReadersStore` over the generated client with only the transport stubbed: the try's stage reaches `?try_stage=`
/// (`wide.compare.same-page-same-crop`, review wide-4 M5), and a refused pick is said after the answer is read again (H3).
@MainActor
final class CompareReadersStoreTests: XCTestCase {
    private final class Transport: URLProtocol {
        nonisolated(unsafe) static var status = 200
        nonisolated(unsafe) static var requests: [URLRequest] = []
        nonisolated(unsafe) static var lines = ""
        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool { request.url?.path.hasPrefix("/api/") == true }
        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            Self.requests.append(request)
            let isPost = request.httpMethod == "POST"
            let body = isPost ? #"{"detail":"moved"}"# : """
            {"page_id":"p1","readers":[{"id":"a","label":"A","kind":"candidate"}],"lines":[\(Self.lines)]}
            """
            let response = HTTPURLResponse(url: request.url!, statusCode: isPost ? Self.status : 200, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func client() -> FicheroClient {
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        Transport.requests = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Transport.self]
        return FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/CompareReadersStoreTests.fichero",
                             session: URLSession(configuration: configuration))
    }

    func testARefusedPickIsSaidAfterTheReadingsAreShownAgain() async {
        Transport.lines = #"{"order":0,"differs":true,"picked_by_person":false,"segment_id":"s1","counting_reader_id":"a","readings":[{"reader_id":"a","text":"x","representation_id":"ra"},{"reader_id":"b","text":"y","representation_id":"rb"}],"words":[]}"#
        Transport.status = 409
        defer { Transport.lines = "" }
        let store = CompareReadersStore(client: client(), pageId: "p1", platform: .mac)
        await store.load()
        await store.pick(readerId: "b", onLine: 0)
        XCTAssertEqual(store.failure, "That line has changed since you looked at it. The readings are shown again.")
        XCTAssertEqual(Transport.requests.filter { $0.httpMethod == "GET" }.count, 2, "the answer is read again")
    }

    func testLoadAsksForTheTrysReadings() async {
        let store = CompareReadersStore(client: client(), pageId: "p1", tryStage: "names", platform: .mac)
        await store.load()
        XCTAssertEqual(Transport.requests.first?.url?.query?.contains("try_stage=names"), true)
        XCTAssertNotNil(store.model)
    }

    func testLoadWithoutATryAsksForTheProjects() async {
        let store = CompareReadersStore(client: client(), pageId: "p1", platform: .mac)
        await store.load()
        XCTAssertEqual(Transport.requests.first?.url?.query?.contains("try_stage") ?? false, false)
    }
}
