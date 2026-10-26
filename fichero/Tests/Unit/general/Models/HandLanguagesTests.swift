@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class HandsRequestURLProtocol: URLProtocol {
    nonisolated(unsafe) static var seen: [URL] = []

    override static func canInit(with request: URLRequest) -> Bool { request.url?.path == "/api/recipes/hands" }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.seen.append(request.url!)
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"items":[]}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// #6118 (`source.onboard.material.which-hand`): Which hand is asked for the project's languages, from the page's own
/// answers, so a Spanish project is not offered Kurrent while the saved answers lag until Continue.
@MainActor
@Suite(.serialized)
struct HandLanguagesTests {
    private func makeStore() -> RecipeSetupStore {
        HandsRequestURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HandsRequestURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                                   session: URLSession(configuration: configuration))
        return RecipeSetupStore(client: client)
    }

    private func languagesAsked(_ url: URL?) -> String? {
        url.flatMap { URLComponents(url: $0, resolvingAgainstBaseURL: false) }?
            .queryItems?.first { $0.name == "languages" }?.value
    }

    @Test("the languages go to the hands query as one comma-separated list, none when none are chosen")
    func languagesQuery() {
        #expect(RecipeSetupStore.handLanguages(["es"]) == "es")
        #expect(RecipeSetupStore.handLanguages(["es", "und-x-quechua"]) == "es,und-x-quechua")
        #expect(RecipeSetupStore.handLanguages([]) == nil)
    }

    @Test("loadHands sends the page's languages with the request, and none when none are chosen")
    func requestCarriesTheLanguages() async {
        let store = makeStore()
        store.languages = ["es", "und-x-quechua"]
        await store.loadHands()
        #expect(languagesAsked(HandsRequestURLProtocol.seen.last) == "es,und-x-quechua")

        store.languages = []
        await store.loadHands()
        #expect(HandsRequestURLProtocol.seen.count == 2)
        #expect(languagesAsked(HandsRequestURLProtocol.seen.last) == nil)
    }
}
