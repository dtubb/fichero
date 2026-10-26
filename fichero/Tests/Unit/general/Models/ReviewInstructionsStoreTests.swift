@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class ReviewInstructionsURLProtocol: URLProtocol {
    nonisolated(unsafe) static var status = 200

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path == "/api/recipes/project/review-instructions"
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let json = Self.status == 200
            ? #"""
              {"passes":[{"lens":"orthography","default":"Check spelling.","text":"Only u/v.","edited":true,
                          "profile":"Built from the generic profile."}]}
              """#
            : #"{"detail":"No project is open."}"#
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// #6128 (`source.job.review-instructions-are-editable`): the app shows the passes the engine lists, default and
/// profile sentence as sent. The engine is a stubbed transport.
@MainActor
@Suite(.serialized)
struct ReviewInstructionsStoreTests {
    private func makeStore(status: Int = 200) -> ReviewInstructionsStore {
        ReviewInstructionsURLProtocol.status = status
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ReviewInstructionsURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                                   session: URLSession(configuration: configuration))
        return ReviewInstructionsStore(client: client)
    }

    @Test("it reads each pass's default, text and profile sentence")
    func readsThePasses() async {
        let store = makeStore()
        await store.load()
        #expect(store.passes.map(\.lens) == ["orthography"])
        #expect(store.passes.first?._default == "Check spelling.")
        #expect(store.passes.first?.edited == true)
        #expect(store.passes.first?.profile == "Built from the generic profile.")
        #expect(store.errorMessage == nil)
    }

    @Test("a refusal is said in the engine's words and no pass is shown")
    func saysTheRefusal() async {
        let store = makeStore(status: 409)
        await store.load()
        #expect(store.passes.isEmpty)
        #expect(store.errorMessage == "No project is open.")
    }
}
